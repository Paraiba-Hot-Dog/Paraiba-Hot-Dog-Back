from collections import OrderedDict
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, noload, selectinload

from src.clientes.model import Cliente
from src.pedidos.model import (
    FormaPagamento,
    ItemPedido,
    ItemPedidoAdicional,
    Pedido,
    StatusItemPedido,
    StatusPedido,
)
from src.pedidos.schema import (
    AdicionarItensPedido,
    AumentarQuantidadeItemPedido,
    AtualizarObservacaoItemPedido,
    AtualizarParaViagemPedido,
    AtualizarStatusCozinha,
    CancelarItemPedido,
    CancelarPedido,
    CozinhaAdicionalRead,
    CozinhaItemRead,
    FinalizarPedido,
    ItemPedidoCreate,
    PedidoCreate,
    PedidoFiltro,
)
from src.produtos.model import OpcaoComplemento, Produto, ProdutoVariacao
from src.unidades.model import Unidade

PONTOS_RESGATE_FIDELIDADE = 10
VALOR_DESCONTO_FIDELIDADE = Decimal("17.00")
# Quantos lotes entregues a aba "Entregues" da cozinha mostra. O historico completo
# continua no banco; o limite existe so para a tela nao crescer sem fim.
LIMITE_ENTREGUES_COZINHA = 30
FUSO_SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def _opcoes_carregamento_pedido(carregar_variacao: bool = False):
    """Carrega itens e adicionais sem arrastar unidade, cliente ou o catalogo completo."""
    if carregar_variacao:
        itens_loader = selectinload(Pedido.itens).options(
            selectinload(ItemPedido.produto_variacao)
            .selectinload(ProdutoVariacao.produto)
            .options(
                noload(Produto.subcategoria),
                noload(Produto.unidades),
                noload(Produto.grupos),
                noload(Produto.variacoes),
            ),
            selectinload(ItemPedido.adicionais).noload(ItemPedidoAdicional.adicional),
        )
    else:
        itens_loader = selectinload(Pedido.itens).options(
            noload(ItemPedido.produto_variacao),
            selectinload(ItemPedido.adicionais).noload(ItemPedidoAdicional.adicional),
        )
    return (
        noload(Pedido.unidade),
        noload(Pedido.cliente),
        itens_loader,
    )


def listar_pedidos(db: Session, filtro: PedidoFiltro) -> list[Pedido]:
    """Lista os pedidos com filtros opcionais de unidade e status, ordenados do mais recente."""
    query = db.query(Pedido).options(*_opcoes_carregamento_pedido())
    if filtro.unidade_id is not None:
        query = query.filter(Pedido.unidade_id == filtro.unidade_id)
    if filtro.status is not None:
        query = query.filter(Pedido.status == filtro.status)
    if filtro.apenas_hoje_ou_abertos:
        inicio_hoje_utc = (
            datetime.now(FUSO_SAO_PAULO)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
        query = query.filter(
            or_(
                Pedido.status == StatusPedido.aberto,
                Pedido.created_at >= inicio_hoje_utc,
            )
        )
    return query.order_by(Pedido.created_at.desc()).offset(filtro.skip).limit(filtro.limit).all()


def obter_pedido(db: Session, pedido_id: int) -> Pedido:
    """Retorna um pedido pelo ID ou lanca 404 se nao encontrado."""
    pedido = (
        db.query(Pedido)
        .options(*_opcoes_carregamento_pedido())
        .filter(Pedido.id == pedido_id)
        .first()
    )
    if not pedido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido nao encontrado")
    return pedido


def _obter_pedido_para_atualizacao(
    db: Session,
    pedido_id: int,
    carregar_variacao: bool = False,
) -> Pedido:
    """Retorna e bloqueia o pedido para atualizacao transacional ou lanca 404."""
    pedido = (
        db.query(Pedido)
        .options(*_opcoes_carregamento_pedido(carregar_variacao=carregar_variacao))
        .filter(Pedido.id == pedido_id)
        .with_for_update(of=Pedido)
        .first()
    )
    if not pedido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido nao encontrado")
    return pedido


def _obter_item_para_atualizacao(db: Session, item_id: int) -> tuple[ItemPedido, Pedido]:
    """Retorna o item e seu pedido bloqueado para atualizacao ou lanca 404."""
    item_info = db.query(ItemPedido.id, ItemPedido.pedido_id).filter(ItemPedido.id == item_id).first()
    if not item_info:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item do pedido nao encontrado")
    pedido = _obter_pedido_para_atualizacao(db, item_info.pedido_id)
    item = next((registro for registro in pedido.itens if registro.id == item_id), None)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item do pedido nao encontrado")
    return item, pedido


def _obter_cliente_para_atualizacao(db: Session, cliente_id: int | None) -> Cliente | None:
    """Retorna e bloqueia o cliente para movimentacao segura de pontos."""
    if cliente_id is None:
        return None
    return db.query(Cliente).filter(Cliente.id == cliente_id).with_for_update().first()


def _validar_pedido_aberto(pedido: Pedido) -> None:
    """Lanca 400 se o pedido nao estiver com status 'aberto'."""
    _validar_pedido_nao_cancelado(pedido)
    if pedido.status != StatusPedido.aberto:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pedido precisa estar aberto",
        )


def _validar_pedido_nao_cancelado(pedido: Pedido) -> None:
    """Lanca 400 se o pedido estiver com status 'cancelado'."""
    if pedido.status == StatusPedido.cancelado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pedido cancelado",
        )


def _validar_pedido_nao_em_preparo(pedido: Pedido) -> None:
    """Impede alteracoes depois que a cozinha inicia o preparo."""
    if any(item.status == StatusItemPedido.preparando for item in pedido.itens):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pedido em preparo nao pode ser alterado",
        )


def _validar_cliente_unidade(db: Session, data: PedidoCreate) -> Cliente | None:
    """Valida existencia da unidade, do cliente e a disponibilidade de pontos de fidelidade."""
    if not db.get(Unidade, data.unidade_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidade nao encontrada")
    cliente = _obter_cliente_para_atualizacao(db, data.cliente_id)
    if data.cliente_id is not None and not cliente:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente nao encontrado")
    if data.usar_desconto_fidelidade:
        if not cliente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Desconto de fidelidade exige cliente cadastrado",
            )
        if cliente.pontos_fidelidade < PONTOS_RESGATE_FIDELIDADE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cliente nao possui pontos suficientes para resgate",
            )
    return cliente


def _validar_variacao_disponivel(
    db: Session,
    unidade_id: int,
    produto_variacao_id: int,
) -> ProdutoVariacao:
    """Verifica se a variacao de produto existe, esta ativa e disponivel para a unidade informada."""
    variacao = db.get(ProdutoVariacao, produto_variacao_id)
    if not variacao:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variacao nao encontrada")
    if not variacao.ativo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Variacao inativa")

    produto = variacao.produto
    if not produto.ativo:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Produto inativo")

    if not produto.disponivel_todas_unidades and unidade_id not in produto.unidade_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Produto indisponivel para esta unidade",
        )

    return variacao


def _nome_variacao(variacao: ProdutoVariacao) -> str:
    """Retorna o nome de exibicao de uma variacao de produto."""
    return variacao.nome


def _obter_adicionais(db: Session, _produto_id: int, adicional_ids: list[int]) -> list[OpcaoComplemento]:
    """Busca e valida as opcoes de complemento pelos IDs fornecidos."""
    if not adicional_ids:
        return []

    opcoes = (
        db.query(OpcaoComplemento)
        .filter(
            OpcaoComplemento.id.in_(adicional_ids),
            OpcaoComplemento.ativo.is_(True),
        )
        .all()
    )
    if len(opcoes) != len(set(adicional_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Opção adicional inválida para o produto",
        )
    return opcoes


def _extrair_sabor_observacao(observacao: str | None) -> str | None:
    if not observacao:
        return None
    for linha in observacao.splitlines():
        linha_limpa = linha.strip()
        if linha_limpa.startswith("Sabor:"):
            return linha_limpa.replace("Sabor:", "").strip()
    return None


def _calcular_acrescimo_combo(db: Session, unidade_id: int, combo_produto_ids: list[int]) -> Decimal:
    """Calcula e valida o adicional de preco dos itens escolhidos no combo."""
    if not combo_produto_ids:
        return Decimal("0")

    ids_unicos = set(combo_produto_ids)
    produtos = (
        db.query(Produto)
        .filter(
            Produto.id.in_(ids_unicos),
            Produto.ativo.is_(True),
            Produto.disponivel_no_combo.is_(True),
        )
        .all()
    )
    if len(produtos) != len(ids_unicos):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Produto invalido ou indisponivel para combo",
        )
    for produto in produtos:
        if not produto.disponivel_todas_unidades and unidade_id not in produto.unidade_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Produto de combo indisponivel para esta unidade",
            )
    por_id = {produto.id: produto for produto in produtos}
    return sum((por_id[pid].valor_adicional_combo or Decimal("0") for pid in combo_produto_ids), Decimal("0"))


def _criar_item(unidade_id: int, data: ItemPedidoCreate, lote: int, db: Session) -> ItemPedido:
    """Cria e retorna um ItemPedido com seus adicionais e acrescimo de combo validados."""
    variacao = _validar_variacao_disponivel(db, unidade_id, data.produto_variacao_id)
    acrescimo_combo = _calcular_acrescimo_combo(db, unidade_id, data.combo_produto_ids)
    nome_gravado = data.produto_nome
    if not nome_gravado:
        sabor = _extrair_sabor_observacao(data.observacao)
        if sabor and sabor not in variacao.produto.nome:
            nome_gravado = f"{variacao.produto.nome} ({sabor})"
        else:
            nome_gravado = variacao.produto.nome

    item = ItemPedido(
        produto_variacao_id=variacao.id,
        produto_variacao=variacao,
        produto_id=variacao.produto_id,
        produto_nome=nome_gravado,
        produto_variacao_nome=_nome_variacao(variacao),
        quantidade=data.quantidade,
        preco_unitario=variacao.preco + acrescimo_combo,
        observacao=data.observacao,
        lote=lote,
    )
    adicionais = _obter_adicionais(db, variacao.produto_id, data.adicional_ids)
    item.adicionais = [
        ItemPedidoAdicional(
            adicional_id=adicional.id,
            nome=adicional.nome,
            preco=adicional.preco,
        )
        for adicional in adicionais
    ]
    return item


def _recalcular_totais(pedido: Pedido) -> None:
    """Recalcula subtotal, desconto de fidelidade e total do pedido com base nos itens nao cancelados."""
    total = Decimal("0")
    for item in pedido.itens:
        if item.status == StatusItemPedido.cancelado:
            continue
        adicionais_total = sum((adicional.preco for adicional in item.adicionais), Decimal("0"))
        total += item.quantidade * (item.preco_unitario + adicionais_total)
    pedido.subtotal = total
    desconto = VALOR_DESCONTO_FIDELIDADE if pedido.pontos_fidelidade_utilizados else Decimal("0")
    pedido.desconto_fidelidade = min(desconto, pedido.subtotal)
    pedido.total = max(pedido.subtotal - pedido.desconto_fidelidade, Decimal("0"))


def _aplicar_pagamento_e_fidelidade(
    pedido: Pedido,
    cliente: Cliente | None,
    forma_pagamento: FormaPagamento,
    para_viagem: bool | None = None,
) -> None:
    """Valida itens, movimenta pontos de fidelidade e marca o pedido como pago."""
    if not any(item.status != StatusItemPedido.cancelado for item in pedido.itens):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pedido sem itens para pagamento")

    if pedido.pontos_fidelidade_utilizados:
        if not cliente:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Desconto de fidelidade exige cliente cadastrado",
            )
        if cliente.pontos_fidelidade < pedido.pontos_fidelidade_utilizados:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cliente nao possui pontos suficientes para resgate",
            )
        cliente.pontos_fidelidade -= pedido.pontos_fidelidade_utilizados

    if cliente is not None and not pedido.pontos_fidelidade_creditados:
        pontos = sum(
            item.quantidade * item.produto_variacao.produto.pontos_fidelidade_por_unidade
            for item in pedido.itens
            if item.status != StatusItemPedido.cancelado
        )
        cliente.pontos_fidelidade += pontos
        pedido.pontos_fidelidade_creditados = True

    if para_viagem is not None:
        pedido.para_viagem = para_viagem

    pedido.status = StatusPedido.pago
    pedido.forma_pagamento = forma_pagamento
    pedido.fechado_em = datetime.utcnow()


def criar_pedido(db: Session, data: PedidoCreate) -> Pedido:
    """Cria um novo pedido com itens iniciais, podendo finalizar o pagamento na mesma transacao."""
    cliente = _validar_cliente_unidade(db, data)
    pedido = Pedido(
        unidade_id=data.unidade_id,
        nome_comanda=data.nome_comanda,
        cliente_id=data.cliente_id,
        observacao=data.observacao,
        para_viagem=data.para_viagem,
        pontos_fidelidade_utilizados=PONTOS_RESGATE_FIDELIDADE if data.usar_desconto_fidelidade else 0,
    )
    pedido.itens = [_criar_item(pedido.unidade_id, item_data, 1, db) for item_data in data.itens]
    _recalcular_totais(pedido)

    if data.forma_pagamento is not None:
        _aplicar_pagamento_e_fidelidade(pedido, cliente, data.forma_pagamento)

    db.add(pedido)
    db.commit()
    return obter_pedido(db, pedido.id)


def adicionar_itens(db: Session, pedido_id: int, data: AdicionarItensPedido) -> Pedido:
    """Adiciona novos itens a um pedido aberto antes de a cozinha iniciar o preparo."""
    pedido = _obter_pedido_para_atualizacao(db, pedido_id)
    _validar_pedido_aberto(pedido)
    _validar_pedido_nao_em_preparo(pedido)

    if data.para_viagem is not None:
        pedido.para_viagem = data.para_viagem

    proximo_lote = max((item.lote for item in pedido.itens), default=0) + 1
    for item_data in data.itens:
        pedido.itens.append(_criar_item(pedido.unidade_id, item_data, proximo_lote, db))
    _recalcular_totais(pedido)

    db.commit()
    return obter_pedido(db, pedido.id)


def atualizar_para_viagem(db: Session, pedido_id: int, data: AtualizarParaViagemPedido) -> Pedido:
    """Atualiza se o pedido inteiro e para viagem enquanto nao estiver cancelado."""
    pedido = _obter_pedido_para_atualizacao(db, pedido_id)
    _validar_pedido_nao_cancelado(pedido)
    pedido.para_viagem = data.para_viagem
    db.commit()
    return obter_pedido(db, pedido.id)


def _copiar_adicionais(item: ItemPedido) -> list[ItemPedidoAdicional]:
    """Cria copias dos adicionais de um item para uso em um novo item de cancelamento parcial."""
    return [
        ItemPedidoAdicional(
            adicional_id=adicional.adicional_id,
            nome=adicional.nome,
            preco=adicional.preco,
        )
        for adicional in item.adicionais
    ]


def aumentar_quantidade_item(db: Session, item_id: int, data: AumentarQuantidadeItemPedido) -> Pedido:
    """Aumenta a quantidade de um item aberto enquanto a cozinha ainda nao iniciou o preparo."""
    item, pedido = _obter_item_para_atualizacao(db, item_id)
    _validar_pedido_aberto(pedido)
    _validar_pedido_nao_em_preparo(pedido)
    if item.status != StatusItemPedido.aberto:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item nao pode ser alterado")

    item.quantidade += data.quantidade
    _recalcular_totais(pedido)
    db.commit()
    return obter_pedido(db, pedido.id)


def atualizar_observacao_item(db: Session, item_id: int, data: AtualizarObservacaoItemPedido) -> Pedido:
    """Atualiza a observacao de um item aberto em pedido aberto antes do preparo."""
    item, pedido = _obter_item_para_atualizacao(db, item_id)
    _validar_pedido_aberto(pedido)
    _validar_pedido_nao_em_preparo(pedido)
    if item.status != StatusItemPedido.aberto:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item nao pode ser alterado")

    item.observacao = data.observacao.strip() or None if data.observacao is not None else None
    db.commit()
    return obter_pedido(db, pedido.id)


def cancelar_item(db: Session, item_id: int, data: CancelarItemPedido) -> Pedido:
    """Cancela total ou parcialmente um item de pedido aberto, registrando motivo e recalculando totais."""
    item, pedido = _obter_item_para_atualizacao(db, item_id)
    _validar_pedido_aberto(pedido)
    _validar_pedido_nao_em_preparo(pedido)

    if item.status == StatusItemPedido.entregue:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item entregue nao pode ser cancelado")
    if item.status == StatusItemPedido.preparando:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item em preparo nao pode ser alterado")
    if item.status == StatusItemPedido.cancelado:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item ja cancelado")

    quantidade_cancelada = data.quantidade or item.quantidade
    if quantidade_cancelada > item.quantidade:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantidade maior que a do item")

    if quantidade_cancelada == item.quantidade:
        item.status = StatusItemPedido.cancelado
        item.motivo_cancelamento = data.motivo_cancelamento
        item.cancelado_em = datetime.utcnow()
    else:
        item.quantidade -= quantidade_cancelada
        item_cancelado = ItemPedido(
            pedido=pedido,
            produto_variacao_id=item.produto_variacao_id,
            produto_id=item.produto_id,
            produto_nome=item.produto_nome,
            produto_variacao_nome=item.produto_variacao_nome,
            quantidade=quantidade_cancelada,
            preco_unitario=item.preco_unitario,
            observacao=item.observacao,
            status=StatusItemPedido.cancelado,
            lote=item.lote,
            motivo_cancelamento=data.motivo_cancelamento,
            cancelado_em=datetime.utcnow(),
            adicionais=_copiar_adicionais(item),
        )
        db.add(item_cancelado)

    _recalcular_totais(pedido)
    if not any(item_pedido.status != StatusItemPedido.cancelado for item_pedido in pedido.itens):
        pedido.status = StatusPedido.cancelado
    db.commit()
    return obter_pedido(db, pedido.id)


def cancelar_pedido(db: Session, pedido_id: int, data: CancelarPedido) -> Pedido:
    """Cancela um pedido nao cancelado, estornando fidelidade e pagamento quando necessario."""
    pedido = _obter_pedido_para_atualizacao(db, pedido_id, carregar_variacao=True)
    _validar_pedido_nao_cancelado(pedido)

    cliente = _obter_cliente_para_atualizacao(db, pedido.cliente_id)
    if pedido.status == StatusPedido.pago and cliente is not None:
        if pedido.pontos_fidelidade_creditados:
            pontos_creditados = sum(
                item.quantidade * item.produto_variacao.produto.pontos_fidelidade_por_unidade
                for item in pedido.itens
                if item.status != StatusItemPedido.cancelado
            )
            cliente.pontos_fidelidade = max(cliente.pontos_fidelidade - pontos_creditados, 0)
            pedido.pontos_fidelidade_creditados = False
        if pedido.pontos_fidelidade_utilizados:
            cliente.pontos_fidelidade += pedido.pontos_fidelidade_utilizados

    for item in pedido.itens:
        if item.status in {StatusItemPedido.aberto, StatusItemPedido.preparando}:
            item.status = StatusItemPedido.cancelado
            item.motivo_cancelamento = data.motivo_cancelamento
            item.cancelado_em = datetime.utcnow()

    pedido.status = StatusPedido.cancelado
    pedido.forma_pagamento = None
    pedido.fechado_em = None

    _recalcular_totais(pedido)
    db.commit()
    return obter_pedido(db, pedido.id)


def finalizar_pedido(db: Session, pedido_id: int, data: FinalizarPedido) -> Pedido:
    """Fecha o pedido com a forma de pagamento informada, deduz e credita pontos de fidelidade."""
    pedido = _obter_pedido_para_atualizacao(db, pedido_id, carregar_variacao=True)
    _validar_pedido_aberto(pedido)
    _recalcular_totais(pedido)

    cliente = _obter_cliente_para_atualizacao(db, pedido.cliente_id)
    _aplicar_pagamento_e_fidelidade(pedido, cliente, data.forma_pagamento, data.para_viagem)

    db.commit()
    return obter_pedido(db, pedido.id)


def _assinatura_adicionais(item: ItemPedido) -> tuple[int | None, ...]:
    """Retorna uma tupla ordenada com os IDs dos adicionais do item para uso como chave de agrupamento."""
    return tuple(sorted(adicional.adicional_id for adicional in item.adicionais))


def _status_grupo(itens: list[ItemPedido]) -> StatusItemPedido:
    """Determina o status consolidado de um grupo de itens da cozinha."""
    if any(item.status == StatusItemPedido.preparando for item in itens):
        return StatusItemPedido.preparando
    if itens and all(item.status == StatusItemPedido.entregue for item in itens):
        return StatusItemPedido.entregue
    return StatusItemPedido.aberto


def listar_cozinha(
    db: Session,
    unidade_id: int | None = None,
    incluir_entregues: bool = False,
    limite_entregues: int = LIMITE_ENTREGUES_COZINHA,
) -> list[CozinhaItemRead]:
    """Lista os itens de preparo agrupados por produto/lote para exibicao na cozinha.

    Por padrao devolve apenas a fila pendente. Com incluir_entregues, acrescenta os
    lotes ja entregues, do mais recente para o mais antigo e limitados a
    limite_entregues, para alimentar a aba "Entregues" sem crescer sem fim.
    """
    status_visiveis = [StatusItemPedido.aberto, StatusItemPedido.preparando]
    if incluir_entregues:
        status_visiveis.append(StatusItemPedido.entregue)

    query = (
        db.query(ItemPedido)
        .options(
            noload(ItemPedido.produto_variacao),
            selectinload(ItemPedido.adicionais).noload(ItemPedidoAdicional.adicional),
            selectinload(ItemPedido.pedido).options(
                noload(Pedido.unidade),
                noload(Pedido.cliente),
            ),
        )
        .join(ItemPedido.pedido)
        .filter(
            Pedido.status != StatusPedido.cancelado,
            ItemPedido.status.in_(status_visiveis),
        )
    )
    if unidade_id is not None:
        query = query.filter(Pedido.unidade_id == unidade_id)

    grupos: OrderedDict[tuple, list[ItemPedido]] = OrderedDict()
    for item in query.order_by(Pedido.created_at.asc(), ItemPedido.lote.asc(), ItemPedido.id.asc()).all():
        chave = (
            item.pedido_id,
            item.produto_variacao_id,
            item.observacao,
            item.lote,
            _assinatura_adicionais(item),
        )
        grupos.setdefault(chave, []).append(item)

    resposta: list[CozinhaItemRead] = []
    for itens in grupos.values():
        primeiro = itens[0]
        resposta.append(
            CozinhaItemRead(
                created_at=primeiro.created_at,
                pedido_id=primeiro.pedido_id,
                nome_comanda=primeiro.pedido.nome_comanda,
                para_viagem=bool(primeiro.pedido.para_viagem),
                lote=primeiro.lote,
                produto_variacao_id=primeiro.produto_variacao_id,
                produto_id=primeiro.produto_id,
                produto_nome=primeiro.produto_nome,
                produto_variacao_nome=primeiro.produto_variacao_nome,
                observacao=primeiro.observacao,
                status=_status_grupo(itens),
                quantidade=sum(item.quantidade for item in itens),
                adicionais=[
                    CozinhaAdicionalRead(
                        adicional_id=adicional.adicional_id,
                        nome=adicional.nome,
                        preco=adicional.preco,
                    )
                    for adicional in primeiro.adicionais
                ],
            )
        )

    pendentes = [grupo for grupo in resposta if grupo.status != StatusItemPedido.entregue]
    if not incluir_entregues:
        return pendentes

    # Os grupos sairam da query em ordem crescente de criacao; invertendo, os
    # entregues mais recentes ficam no topo antes de aplicar o limite.
    entregues = [grupo for grupo in resposta if grupo.status == StatusItemPedido.entregue]
    entregues.reverse()
    return pendentes + entregues[:limite_entregues]


def atualizar_status_cozinha(db: Session, data: AtualizarStatusCozinha) -> list[ItemPedido]:
    """Atualiza o status de todos os itens de um lote de um pedido na cozinha."""
    if data.status not in {StatusItemPedido.preparando, StatusItemPedido.entregue}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status de cozinha invalido",
        )

    pedido = _obter_pedido_para_atualizacao(db, data.pedido_id)
    _validar_pedido_nao_cancelado(pedido)

    itens_lote = [item for item in pedido.itens if item.lote == data.lote]
    if not itens_lote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote de cozinha nao encontrado")

    # Idempotencia: a tela da cozinha pode reenviar o mesmo status (clique duplo ou
    # retry) e isso nao deve virar erro depois que o lote ja saiu da fila.
    if all(item.status == data.status for item in itens_lote):
        return itens_lote

    itens = [
        item
        for item in itens_lote
        if item.status in {StatusItemPedido.aberto, StatusItemPedido.preparando}
    ]
    if not itens:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote de cozinha nao encontrado")

    for item in itens:
        item.status = data.status

    db.commit()
    pedido_atualizado = obter_pedido(db, pedido.id)
    ids_retornados = {item.id for item in itens}
    return [item for item in pedido_atualizado.itens if item.id in ids_retornados]
