from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session, selectinload

from src.bi.schema import (
    BiDashboardRead,
    BiDestaqueRead,
    BiKpiRead,
    BiMixProdutoRead,
    BiProdutoRead,
    BiVendaHoraRead,
)
from src.pedidos.model import ItemPedido, Pedido, StatusItemPedido, StatusPedido


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


def _totais_pedidos(pedidos: list[Pedido]) -> tuple[Decimal, Decimal, int, Decimal]:
    receita_bruta = _money(sum((pedido.subtotal for pedido in pedidos), Decimal("0")))
    lucro_liquido = _money(sum((pedido.total for pedido in pedidos), Decimal("0")))
    total_pedidos = len(pedidos)
    ticket_medio = _money(receita_bruta / total_pedidos) if total_pedidos else Decimal("0.00")
    return receita_bruta, lucro_liquido, total_pedidos, ticket_medio


def _variacoes_mensais(pedidos: list[Pedido], agora: datetime) -> dict[str, Decimal]:
    ano_anterior, mes_anterior = _mes_anterior(agora)
    pedidos_mes_atual = _pedidos_do_mes(pedidos, agora.year, agora.month)
    pedidos_mes_anterior = _pedidos_do_mes(pedidos, ano_anterior, mes_anterior)
    receita_atual = sum((pedido.subtotal for pedido in pedidos_mes_atual), Decimal("0"))
    receita_anterior = sum((pedido.subtotal for pedido in pedidos_mes_anterior), Decimal("0"))
    lucro_atual = sum((pedido.total for pedido in pedidos_mes_atual), Decimal("0"))
    lucro_anterior = sum((pedido.total for pedido in pedidos_mes_anterior), Decimal("0"))
    ticket_atual = receita_atual / len(pedidos_mes_atual) if pedidos_mes_atual else Decimal("0")
    ticket_anterior = receita_anterior / len(pedidos_mes_anterior) if pedidos_mes_anterior else Decimal("0")

    return {
        "variacao_receita_bruta": _variacao(receita_atual, receita_anterior),
        "variacao_lucro_liquido": _variacao(lucro_atual, lucro_anterior),
        "variacao_ticket_medio": _variacao(ticket_atual, ticket_anterior),
        "variacao_total_pedidos": _variacao(Decimal(len(pedidos_mes_atual)), Decimal(len(pedidos_mes_anterior))),
    }


def _resumo_kpis(pedidos: list[Pedido], agora: datetime) -> BiKpiRead:
    receita_bruta, lucro_liquido, total_pedidos, ticket_medio = _totais_pedidos(pedidos)
    return BiKpiRead(
        receita_bruta=receita_bruta,
        lucro_liquido=lucro_liquido,
        ticket_medio=ticket_medio,
        total_pedidos=total_pedidos,
        **_variacoes_mensais(pedidos, agora),
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
) -> tuple[list[BiVendaHoraRead], list[BiProdutoRead]]:
    vendas_por_hora = defaultdict(int)
    produtos: dict[int, dict[str, Decimal | int | str]] = {}
    ano_anterior, mes_anterior = _mes_anterior(agora)

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
            if pedido.created_at.year == agora.year and pedido.created_at.month == agora.month:
                produto["receita_atual"] = Decimal(produto["receita_atual"]) + receita_item
            if pedido.created_at.year == ano_anterior and pedido.created_at.month == mes_anterior:
                produto["receita_anterior"] = Decimal(produto["receita_anterior"]) + receita_item

    return _vendas_por_hora(vendas_por_hora), _top_produtos(produtos)


def _vendas_por_hora(vendas_por_hora: dict[int, int]) -> list[BiVendaHoraRead]:
    maior_volume = max(vendas_por_hora.values(), default=0)
    return [
        BiVendaHoraRead(
            hora=f"{hora:02d}h",
            quantidade=vendas_por_hora.get(hora, 0),
            destaque=bool(maior_volume and vendas_por_hora.get(hora, 0) == maior_volume),
        )
        for hora in range(10, 22)
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


def obter_dashboard(
    db: Session,
    unidade_id: int | None = None,
    ano: int | None = None,
    mes: int | None = None,
    fechamento_mes: bool = False,
) -> BiDashboardRead:
    agora = datetime.now()
    pedidos = _pedidos_validos(db, unidade_id)

    if fechamento_mes:
        ref_ano, ref_mes = _mes_anterior(agora)
        agora_ref = agora.replace(year=ref_ano, month=ref_mes, day=1)
        pedidos_filtrados = [p for p in pedidos if p.created_at.year == ref_ano]
        pedidos_kpi = _pedidos_do_mes(pedidos_filtrados, ref_ano, ref_mes)
    elif mes is not None:
        ref_ano = ano if ano is not None else agora.year
        agora_ref = agora.replace(year=ref_ano, month=mes, day=1)
        pedidos_filtrados = [p for p in pedidos if p.created_at.year == ref_ano]
        pedidos_kpi = _pedidos_do_mes(pedidos_filtrados, ref_ano, mes)
    elif ano is not None:
        agora_ref = agora.replace(year=ano, day=1)
        pedidos_kpi = [p for p in pedidos if p.created_at.year == ano]
    else:
        agora_ref = agora
        pedidos_kpi = pedidos

    resumo = _resumo_kpis(pedidos_kpi, agora_ref)
    vendas_hora, top_produtos = _produtos_vendidos(pedidos_kpi, agora_ref)

    return BiDashboardRead(
        kpis=resumo,
        vendas_por_hora=vendas_hora,
        top_produtos=top_produtos,
        mix_produtos=_mix_produtos(top_produtos),
        vendas_totais=resumo.receita_bruta,
        pedidos_registrados=resumo.total_pedidos,
        destaque=_destaque(top_produtos, pedidos_kpi, resumo.receita_bruta, resumo.lucro_liquido),
    )
