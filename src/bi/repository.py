from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import NamedTuple

from sqlalchemy.orm import Session, selectinload

from src.bi.schema import (
    BiClienteFidelidadeRead,
    BiDashboardRead,
    BiDestaqueRead,
    BiFidelidadeRead,
    BiKpiRead,
    BiMixProdutoRead,
    BiProdutoRead,
    BiUnidadeRead,
    BiVendaHoraRead,
    BiVendaPeriodoRead,
)
from src.pedidos.model import ItemPedido, Pedido, StatusItemPedido, StatusPedido

LIMITE_DIAS_AGRUPAMENTO_DIARIO = 62
LIMITE_TOP_CLIENTES = 5


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _percent(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _item_total(item: ItemPedido) -> Decimal:
    adicionais = sum((adicional.preco for adicional in item.adicionais), Decimal("0"))
    return Decimal(item.quantidade) * (item.preco_unitario + adicionais)


def _variacao(atual: Decimal, anterior: Decimal) -> Decimal:
    if anterior == 0:
        return Decimal("100.00") if atual > 0 else Decimal("0.00")
    return _percent(((atual - anterior) / anterior) * Decimal("100"))


def _mes_anterior(momento: datetime) -> tuple[int, int]:
    if momento.month == 1:
        return momento.year - 1, 12
    return momento.year, momento.month - 1


def _limites_mes(ano: int, mes: int) -> tuple[date, date]:
    return date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])


def _intervalo_anterior(inicio: date, fim: date) -> tuple[date, date]:
    """Retorna o periodo imediatamente anterior com a mesma quantidade de dias."""
    dias = (fim - inicio).days + 1
    fim_anterior = inicio - timedelta(days=1)
    return fim_anterior - timedelta(days=dias - 1), fim_anterior


def _pedidos_validos(db: Session, unidade_id: int | None) -> list[Pedido]:
    query = (
        db.query(Pedido)
        .options(
            selectinload(Pedido.itens).selectinload(ItemPedido.adicionais),
        )
        .filter(Pedido.status != StatusPedido.cancelado)
    )
    if unidade_id is not None:
        query = query.filter(Pedido.unidade_id == unidade_id)
    return query.order_by(Pedido.created_at.asc()).all()


def _pedidos_do_mes(pedidos: list[Pedido], ano: int, mes: int) -> list[Pedido]:
    return [pedido for pedido in pedidos if pedido.created_at.year == ano and pedido.created_at.month == mes]


def _pedidos_no_intervalo(pedidos: list[Pedido], inicio: date, fim: date) -> list[Pedido]:
    return [pedido for pedido in pedidos if inicio <= pedido.created_at.date() <= fim]


def _totais_pedidos(pedidos: list[Pedido]) -> tuple[Decimal, Decimal, int, Decimal]:
    receita_bruta = _money(sum((pedido.subtotal for pedido in pedidos), Decimal("0")))
    lucro_liquido = _money(sum((pedido.total for pedido in pedidos), Decimal("0")))
    total_pedidos = len(pedidos)
    ticket_medio = _money(receita_bruta / total_pedidos) if total_pedidos else Decimal("0.00")
    return receita_bruta, lucro_liquido, total_pedidos, ticket_medio


def _variacoes_entre(pedidos_atuais: list[Pedido], pedidos_anteriores: list[Pedido]) -> dict[str, Decimal]:
    receita_atual = sum((pedido.subtotal for pedido in pedidos_atuais), Decimal("0"))
    receita_anterior = sum((pedido.subtotal for pedido in pedidos_anteriores), Decimal("0"))
    lucro_atual = sum((pedido.total for pedido in pedidos_atuais), Decimal("0"))
    lucro_anterior = sum((pedido.total for pedido in pedidos_anteriores), Decimal("0"))
    ticket_atual = receita_atual / len(pedidos_atuais) if pedidos_atuais else Decimal("0")
    ticket_anterior = receita_anterior / len(pedidos_anteriores) if pedidos_anteriores else Decimal("0")

    return {
        "variacao_receita_bruta": _variacao(receita_atual, receita_anterior),
        "variacao_lucro_liquido": _variacao(lucro_atual, lucro_anterior),
        "variacao_ticket_medio": _variacao(ticket_atual, ticket_anterior),
        "variacao_total_pedidos": _variacao(Decimal(len(pedidos_atuais)), Decimal(len(pedidos_anteriores))),
    }


def _variacoes_mensais(pedidos: list[Pedido], agora: datetime) -> dict[str, Decimal]:
    ano_anterior, mes_anterior = _mes_anterior(agora)
    return _variacoes_entre(
        _pedidos_do_mes(pedidos, agora.year, agora.month),
        _pedidos_do_mes(pedidos, ano_anterior, mes_anterior),
    )


def _resumo_kpis(
    pedidos: list[Pedido],
    agora: datetime,
    pedidos_anteriores: list[Pedido] | None = None,
) -> BiKpiRead:
    receita_bruta, lucro_liquido, total_pedidos, ticket_medio = _totais_pedidos(pedidos)
    variacoes = (
        _variacoes_mensais(pedidos, agora)
        if pedidos_anteriores is None
        else _variacoes_entre(pedidos, pedidos_anteriores)
    )
    return BiKpiRead(
        receita_bruta=receita_bruta,
        lucro_liquido=lucro_liquido,
        ticket_medio=ticket_medio,
        total_pedidos=total_pedidos,
        **variacoes,
    )


def _pedido_total_itens(pedido: Pedido) -> Decimal:
    return sum(
        (
            _item_total(item)
            for item in pedido.itens
            if item.status != StatusItemPedido.cancelado
        ),
        Decimal("0"),
    )


def _receita_liquida_item(pedido: Pedido, receita_item: Decimal, receita_pedido: Decimal) -> Decimal:
    if not receita_pedido:
        return Decimal("0")
    return (receita_item / receita_pedido) * pedido.total


def _produtos_vendidos(
    pedidos: list[Pedido],
    agora: datetime,
    pedidos_anteriores: list[Pedido] | None = None,
) -> tuple[list[BiVendaHoraRead], list[BiProdutoRead]]:
    """Agrupa os itens vendidos por hora e por produto.

    Sem ``pedidos_anteriores`` a variacao compara o mes de ``agora`` com o mes
    anterior; com eles, compara todo o periodo com o periodo anterior informado.
    """
    vendas_por_hora = defaultdict(int)
    produtos: dict[int, dict[str, Decimal | int | str]] = {}
    ano_anterior, mes_anterior = _mes_anterior(agora)
    comparar_periodos = pedidos_anteriores is not None

    for pedido in pedidos:
        receita_pedido = _pedido_total_itens(pedido)
        for item in pedido.itens:
            if item.status == StatusItemPedido.cancelado:
                continue

            receita_item = _item_total(item)
            vendas_por_hora[pedido.created_at.hour] += item.quantidade
            produto = produtos.setdefault(
                item.produto_id,
                {
                    "nome": item.produto_nome,
                    "quantidade": 0,
                    "receita": Decimal("0"),
                    "receita_liquida": Decimal("0"),
                    "receita_atual": Decimal("0"),
                    "receita_anterior": Decimal("0"),
                },
            )
            produto["quantidade"] = int(produto["quantidade"]) + item.quantidade
            produto["receita"] = Decimal(produto["receita"]) + receita_item
            produto["receita_liquida"] = Decimal(produto["receita_liquida"]) + _receita_liquida_item(
                pedido,
                receita_item,
                receita_pedido,
            )
            if comparar_periodos or (
                pedido.created_at.year == agora.year and pedido.created_at.month == agora.month
            ):
                produto["receita_atual"] = Decimal(produto["receita_atual"]) + receita_item
            if not comparar_periodos and (
                pedido.created_at.year == ano_anterior and pedido.created_at.month == mes_anterior
            ):
                produto["receita_anterior"] = Decimal(produto["receita_anterior"]) + receita_item

    for pedido in pedidos_anteriores or []:
        for item in pedido.itens:
            if item.status == StatusItemPedido.cancelado or item.produto_id not in produtos:
                continue
            produto = produtos[item.produto_id]
            produto["receita_anterior"] = Decimal(produto["receita_anterior"]) + _item_total(item)

    return _vendas_por_hora(vendas_por_hora), _top_produtos(produtos)


def _vendas_por_hora(vendas_por_hora: dict[int, int]) -> list[BiVendaHoraRead]:
    maior_volume = max(vendas_por_hora.values(), default=0)
    hora_inicial = min([10, *vendas_por_hora.keys()])
    hora_final = max([21, *vendas_por_hora.keys()])
    return [
        BiVendaHoraRead(
            hora=f"{hora:02d}h",
            quantidade=vendas_por_hora.get(hora, 0),
            destaque=bool(maior_volume and vendas_por_hora.get(hora, 0) == maior_volume),
        )
        for hora in range(hora_inicial, hora_final + 1)
    ]


def _top_produtos(produtos: dict[int, dict[str, Decimal | int | str]]) -> list[BiProdutoRead]:
    produtos_ordenados = sorted(
        produtos.items(),
        key=lambda item: (int(item[1]["quantidade"]), Decimal(item[1]["receita"])),
        reverse=True,
    )
    return [
        BiProdutoRead(
            rank=indice,
            produto_id=produto_id,
            nome=str(dados["nome"]),
            quantidade=int(dados["quantidade"]),
            receita=_money(Decimal(dados["receita"])),
            variacao=_variacao(Decimal(dados["receita_atual"]), Decimal(dados["receita_anterior"])),
        )
        for indice, (produto_id, dados) in enumerate(produtos_ordenados[:10], start=1)
    ]


def _mix_produtos(top_produtos: list[BiProdutoRead]) -> list[BiMixProdutoRead]:
    quantidade_total = sum((produto.quantidade for produto in top_produtos), 0)
    return [
        BiMixProdutoRead(
            nome=produto.nome,
            percentual=_percent((Decimal(produto.quantidade) / quantidade_total) * Decimal("100"))
            if quantidade_total
            else Decimal("0.00"),
        )
        for produto in top_produtos[:3]
    ]


def _destaque(
    top_produtos: list[BiProdutoRead],
    produtos: list[Pedido],
    receita_bruta: Decimal,
    lucro_liquido: Decimal,
) -> BiDestaqueRead | None:
    if not top_produtos:
        return None

    principal = top_produtos[0]
    receita_liquida = _produto_receita_liquida(principal.produto_id, produtos)
    margem_ganho = _percent((principal.receita / receita_bruta) * Decimal("100")) if receita_bruta else Decimal("0.00")
    margem_liquida = (
        _percent((receita_liquida / lucro_liquido) * Decimal("100")) if lucro_liquido else Decimal("0.00")
    )
    return BiDestaqueRead(
        nome=principal.nome,
        margem_ganho=margem_ganho,
        margem_liquida=margem_liquida,
    )


def _produto_receita_liquida(produto_id: int, pedidos: list[Pedido]) -> Decimal:
    receita_liquida = Decimal("0")
    for pedido in pedidos:
        receita_pedido = _pedido_total_itens(pedido)
        for item in pedido.itens:
            if item.status == StatusItemPedido.cancelado or item.produto_id != produto_id:
                continue
            receita_liquida += _receita_liquida_item(pedido, _item_total(item), receita_pedido)
    return _money(receita_liquida)


def _vendas_por_periodo(
    pedidos: list[Pedido],
    inicio: date | None,
    fim: date | None,
) -> tuple[str, list[BiVendaPeriodoRead]]:
    """Serie de vendas do periodo, por dia em intervalos curtos e por mes nos longos."""
    if inicio is None or fim is None:
        if not pedidos:
            return "dia", []
        inicio, fim = pedidos[0].created_at.date(), pedidos[-1].created_at.date()

    agrupar_por_dia = (fim - inicio).days <= LIMITE_DIAS_AGRUPAMENTO_DIARIO
    formato = "%Y-%m-%d" if agrupar_por_dia else "%Y-%m"
    receitas: dict[str, Decimal] = defaultdict(Decimal)
    quantidades: dict[str, int] = defaultdict(int)
    for pedido in pedidos:
        chave = pedido.created_at.strftime(formato)
        receitas[chave] += pedido.subtotal
        quantidades[chave] += 1

    chaves: list[str] = []
    if agrupar_por_dia:
        dia = inicio
        while dia <= fim:
            chaves.append(dia.strftime(formato))
            dia += timedelta(days=1)
    else:
        ano, mes = inicio.year, inicio.month
        while (ano, mes) <= (fim.year, fim.month):
            chaves.append(f"{ano:04d}-{mes:02d}")
            ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)

    return (
        "dia" if agrupar_por_dia else "mes",
        [
            BiVendaPeriodoRead(
                periodo=chave,
                receita_bruta=_money(receitas.get(chave, Decimal("0"))),
                total_pedidos=quantidades.get(chave, 0),
            )
            for chave in chaves
        ],
    )


def _desempenho_unidades(pedidos: list[Pedido]) -> list[BiUnidadeRead]:
    pedidos_por_unidade: dict[int, list[Pedido]] = defaultdict(list)
    for pedido in pedidos:
        pedidos_por_unidade[pedido.unidade_id].append(pedido)

    receita_total = sum((pedido.subtotal for pedido in pedidos), Decimal("0"))
    unidades = []
    for unidade_id, pedidos_unidade in pedidos_por_unidade.items():
        receita_bruta, lucro_liquido, total_pedidos, ticket_medio = _totais_pedidos(pedidos_unidade)
        unidade = pedidos_unidade[0].unidade
        unidades.append(
            BiUnidadeRead(
                unidade_id=unidade_id,
                nome=unidade.nome if unidade else f"Unidade {unidade_id}",
                total_pedidos=total_pedidos,
                receita_bruta=receita_bruta,
                lucro_liquido=lucro_liquido,
                ticket_medio=ticket_medio,
                participacao=_percent((receita_bruta / receita_total) * Decimal("100"))
                if receita_total
                else Decimal("0.00"),
            )
        )
    return sorted(unidades, key=lambda unidade: unidade.receita_bruta, reverse=True)


def _fidelidade(pedidos: list[Pedido]) -> BiFidelidadeRead:
    pedidos_com_cliente = [pedido for pedido in pedidos if pedido.cliente_id is not None]
    pedidos_sem_cliente = [pedido for pedido in pedidos if pedido.cliente_id is None]

    clientes: dict[int, dict[str, Decimal | int | str]] = {}
    for pedido in pedidos_com_cliente:
        cliente = clientes.setdefault(
            pedido.cliente_id,
            {
                "nome": pedido.cliente.nome if pedido.cliente else f"Cliente {pedido.cliente_id}",
                "pontos_atuais": pedido.cliente.pontos_fidelidade if pedido.cliente else 0,
                "total_pedidos": 0,
                "receita_bruta": Decimal("0"),
            },
        )
        cliente["total_pedidos"] = int(cliente["total_pedidos"]) + 1
        cliente["receita_bruta"] = Decimal(cliente["receita_bruta"]) + pedido.subtotal

    top_clientes = sorted(
        clientes.items(),
        key=lambda item: (Decimal(item[1]["receita_bruta"]), int(item[1]["total_pedidos"])),
        reverse=True,
    )[:LIMITE_TOP_CLIENTES]

    return BiFidelidadeRead(
        pedidos_com_cliente=len(pedidos_com_cliente),
        percentual_pedidos_com_cliente=_percent(
            (Decimal(len(pedidos_com_cliente)) / Decimal(len(pedidos))) * Decimal("100")
        )
        if pedidos
        else Decimal("0.00"),
        clientes_unicos=len(clientes),
        pontos_resgatados=sum((pedido.pontos_fidelidade_utilizados for pedido in pedidos), 0),
        descontos_concedidos=_money(sum((pedido.desconto_fidelidade for pedido in pedidos), Decimal("0"))),
        ticket_medio_com_cliente=_totais_pedidos(pedidos_com_cliente)[3],
        ticket_medio_sem_cliente=_totais_pedidos(pedidos_sem_cliente)[3],
        top_clientes=[
            BiClienteFidelidadeRead(
                cliente_id=cliente_id,
                nome=str(dados["nome"]),
                total_pedidos=int(dados["total_pedidos"]),
                receita_bruta=_money(Decimal(dados["receita_bruta"])),
                pontos_atuais=int(dados["pontos_atuais"]),
            )
            for cliente_id, dados in top_clientes
        ],
    )


class _PeriodoFiltrado(NamedTuple):
    pedidos: list[Pedido]
    agora_ref: datetime
    pedidos_anteriores: list[Pedido] | None = None
    inicio: date | None = None
    fim: date | None = None


def _filtrar_periodo(
    pedidos: list[Pedido],
    *,
    ano: int | None,
    mes: int | None,
    fechamento_mes: bool,
    data_inicio: date | None,
    data_fim: date | None,
) -> _PeriodoFiltrado:
    """Aplica o filtro de periodo.

    ``data_inicio``/``data_fim`` tem prioridade sobre os demais filtros e fazem as
    variacoes compararem com o periodo anterior de mesma duracao.
    """
    agora = datetime.now()

    if data_inicio is not None and data_fim is not None:
        return _PeriodoFiltrado(
            pedidos=_pedidos_no_intervalo(pedidos, data_inicio, data_fim),
            agora_ref=datetime.combine(data_fim, agora.time()),
            pedidos_anteriores=_pedidos_no_intervalo(pedidos, *_intervalo_anterior(data_inicio, data_fim)),
            inicio=data_inicio,
            fim=data_fim,
        )
    if fechamento_mes or mes is not None:
        if fechamento_mes:
            ref_ano, ref_mes = _mes_anterior(agora)
        else:
            ref_ano, ref_mes = (ano if ano is not None else agora.year), mes
        return _PeriodoFiltrado(
            pedidos=_pedidos_do_mes(pedidos, ref_ano, ref_mes),
            agora_ref=agora.replace(year=ref_ano, month=ref_mes, day=1),
            inicio=_limites_mes(ref_ano, ref_mes)[0],
            fim=_limites_mes(ref_ano, ref_mes)[1],
        )
    if ano is not None:
        return _PeriodoFiltrado(
            pedidos=[pedido for pedido in pedidos if pedido.created_at.year == ano],
            agora_ref=agora.replace(year=ano, day=1),
            inicio=date(ano, 1, 1),
            fim=date(ano, 12, 31),
        )
    return _PeriodoFiltrado(pedidos=pedidos, agora_ref=agora)


def obter_dashboard(
    db: Session,
    *,
    unidade_id: int | None = None,
    ano: int | None = None,
    mes: int | None = None,
    fechamento_mes: bool = False,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> BiDashboardRead:
    """Monta o dashboard de BI para a unidade e o periodo informados."""
    periodo = _filtrar_periodo(
        _pedidos_validos(db, unidade_id),
        ano=ano,
        mes=mes,
        fechamento_mes=fechamento_mes,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
    pedidos = periodo.pedidos
    resumo = _resumo_kpis(pedidos, periodo.agora_ref, periodo.pedidos_anteriores)
    vendas_hora, top_produtos = _produtos_vendidos(pedidos, periodo.agora_ref, periodo.pedidos_anteriores)
    agrupamento_periodo, vendas_periodo = _vendas_por_periodo(pedidos, periodo.inicio, periodo.fim)

    return BiDashboardRead(
        kpis=resumo,
        vendas_por_hora=vendas_hora,
        top_produtos=top_produtos,
        mix_produtos=_mix_produtos(top_produtos),
        vendas_totais=resumo.receita_bruta,
        pedidos_registrados=resumo.total_pedidos,
        destaque=_destaque(top_produtos, pedidos, resumo.receita_bruta, resumo.lucro_liquido),
        agrupamento_periodo=agrupamento_periodo,
        vendas_por_periodo=vendas_periodo,
        desempenho_unidades=_desempenho_unidades(pedidos),
        fidelidade=_fidelidade(pedidos),
    )
