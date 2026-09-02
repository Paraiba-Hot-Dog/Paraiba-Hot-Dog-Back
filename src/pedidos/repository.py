from collections import OrderedDict
from datetime import datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

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
from src.produtos.model import ProdutoAdicional, ProdutoVariacao
from src.unidades.model import Unidade

PONTOS_RESGATE_FIDELIDADE = 12
VALOR_DESCONTO_FIDELIDADE = Decimal("17.00")


def listar_pedidos(db: Session, filtro: PedidoFiltro) -> list[Pedido]:
    """Lista os pedidos com filtros opcionais de unidade e status, ordenados do mais recente."""
    query = db.query(Pedido)
    if filtro.unidade_id is not None:
        query = query.filter(Pedido.unidade_id == filtro.unidade_id)
    if filtro.status is not None:
        query = query.filter(Pedido.status == filtro.status)
    return query.order_by(Pedido.created_at.desc()).offset(filtro.skip).limit(filtro.limit).all()


def obter_pedido(db: Session, pedido_id: int) -> Pedido:
    """Retorna um pedido pelo ID ou lanca 404 se nao encontrado."""
    pedido = db.get(Pedido, pedido_id)
    if not pedido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pedido nao encontrado")
    return pedido


def obter_item(db: Session, item_id: int) -> ItemPedido:
    """Retorna um item de pedido pelo ID ou lanca 404 se nao encontrado."""
    item = db.get(ItemPedido, item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item do pedido nao encontrado")
    return item


def _validar_pedido_aberto(pedido: Pedido) -> None:
    """Lanca 400 se o pedido nao estiver com status 'aberto'."""
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


def _reabrir_pedido_pago(db: Session, pedido: Pedido) -> None:
    """Estorna fidelidade e pagamento para permitir alteracoes em um pedido pago."""
    if pedido.status != StatusPedido.pago:
        return

    cliente = db.get(Cliente, pedido.cliente_id) if pedido.cliente_id is not None else None
    if cliente is not None and pedido.pontos_fidelidade_creditados:
        pontos_creditados = sum(
            item.quantidade * item.produto_variacao.produto.pontos_fidelidade_por_unidade
            for item in pedido.itens
            if item.status != StatusItemPedido.cancelado
        )
        cliente.pontos_fidelidade = max(cliente.pontos_fidelidade - pontos_creditados, 0)
        pedido.pontos_fidelidade_creditados = False
    if cliente is not None and pedido.pontos_fidelidade_utilizados:
        cliente.pontos_fidelidade += pedido.pontos_fidelidade_utilizados

    pedido.status = StatusPedido.aberto
    pedido.forma_pagamento = None
    pedido.fechado_em = None


def _validar_cliente_unidade(db: Session, data: PedidoCreate) -> None:
    """Valida existencia da unidade, do cliente e a disponibilidade de pontos de fidelidade."""
    if not db.get(Unidade, data.unidade_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidade nao encontrada")
    cliente = db.get(Cliente, data.cliente_id) if data.cliente_id is not None else None
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


def _obter_adicionais(db: Session, produto_id: int, adicional_ids: list[int]) -> list[ProdutoAdicional]:
    """Busca e valida os adicionais de um produto pelos IDs fornecidos, lancando 400 se invalidos."""
    if not adicional_ids:
        return []

    adicionais = (
        db.query(ProdutoAdicional)
        .filter(
            ProdutoAdicional.id.in_(adicional_ids),
            ProdutoAdicional.produto_id == produto_id,
        )
        .all()
    )
    if len(adicionais) != len(set(adicional_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Adicional invalido para o produto",
        )
    return adicionais


def _criar_item(pedido: Pedido, data: ItemPedidoCreate, lote: int, db: Session) -> ItemPedido:
    """Cria e retorna um ItemPedido com seus adicionais a partir dos dados de criacao."""
    variacao = _validar_variacao_disponivel(db, pedido.unidade_id, data.produto_variacao_id)
    item = ItemPedido(
        pedido=pedido,
        produto_variacao_id=variacao.id,
        produto_id=variacao.produto_id,
        produto_nome=variacao.produto.nome,
        produto_variacao_nome=_nome_variacao(variacao),
        quantidade=data.quantidade,
        preco_unitario=variacao.preco,
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


def criar_pedido(db: Session, data: PedidoCreate) -> Pedido:
    """Cria um novo pedido com seus itens iniciais, aplicando desconto de fidelidade se solicitado."""
    _validar_cliente_unidade(db, data)
    pedido = Pedido(
        unidade_id=data.unidade_id,
        nome_comanda=data.nome_comanda,
        cliente_id=data.cliente_id,
        observacao=data.observacao,
        pontos_fidelidade_utilizados=PONTOS_RESGATE_FIDELIDADE if data.usar_desconto_fidelidade else 0,
    )
    pedido.itens = [_criar_item(pedido, item_data, 1, db) for item_data in data.itens]
    _recalcular_totais(pedido)

    db.add(pedido)
    db.commit()
    db.refresh(pedido)
    return pedido


def adicionar_itens(db: Session, pedido_id: int, data: AdicionarItensPedido) -> Pedido:
    """Adiciona itens e reabre o pedido pago quando a cozinha ainda permite alteracoes."""
    pedido = obter_pedido(db, pedido_id)
    _validar_pedido_nao_cancelado(pedido)
    _validar_pedido_nao_em_preparo(pedido)
    _reabrir_pedido_pago(db, pedido)

    proximo_lote = max((item.lote for item in pedido.itens), default=0) + 1
    for item_data in data.itens:
        pedido.itens.append(_criar_item(pedido, item_data, proximo_lote, db))
    _recalcular_totais(pedido)

    db.commit()
    db.refresh(pedido)
    return pedido


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
    """Aumenta a quantidade de um item enquanto a cozinha ainda nao iniciou o preparo."""
    item = obter_item(db, item_id)
    pedido = item.pedido
    _validar_pedido_nao_cancelado(pedido)
    _validar_pedido_nao_em_preparo(pedido)
    if item.status != StatusItemPedido.aberto:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item nao pode ser alterado")

    _reabrir_pedido_pago(db, pedido)
    item.quantidade += data.quantidade
    _recalcular_totais(pedido)
    db.commit()
    db.refresh(pedido)
    return pedido


def cancelar_item(db: Session, item_id: int, data: CancelarItemPedido) -> Pedido:
    """Cancela total ou parcialmente um item do pedido, registrando o motivo e recalculando totais."""
    item = obter_item(db, item_id)
    pedido = item.pedido
    _validar_pedido_nao_cancelado(pedido)
    _validar_pedido_nao_em_preparo(pedido)

    if item.status == StatusItemPedido.entregue:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item entregue nao pode ser cancelado")
    if item.status == StatusItemPedido.preparando:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item em preparo nao pode ser alterado")
    if item.status == StatusItemPedido.cancelado:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Item ja cancelado")

    _reabrir_pedido_pago(db, pedido)

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
    db.refresh(pedido)
    return pedido


def cancelar_pedido(db: Session, pedido_id: int, data: CancelarPedido) -> Pedido:
    """Cancela um pedido nao cancelado, estornando fidelidade e pagamento quando necessario."""
    pedido = obter_pedido(db, pedido_id)
    _validar_pedido_nao_cancelado(pedido)

    cliente = db.get(Cliente, pedido.cliente_id) if pedido.cliente_id is not None else None
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
    db.refresh(pedido)
    return pedido


def finalizar_pedido(db: Session, pedido_id: int, data: FinalizarPedido) -> Pedido:
    """Fecha o pedido com a forma de pagamento informada, deduz e credita pontos de fidelidade."""
    pedido = obter_pedido(db, pedido_id)
    _validar_pedido_aberto(pedido)
    _recalcular_totais(pedido)

    if not any(item.status != StatusItemPedido.cancelado for item in pedido.itens):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pedido sem itens para pagamento")

    cliente = db.get(Cliente, pedido.cliente_id) if pedido.cliente_id is not None else None
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

    pedido.status = StatusPedido.pago
    pedido.forma_pagamento = data.forma_pagamento
    pedido.fechado_em = datetime.utcnow()

    db.commit()
    db.refresh(pedido)
    return pedido


def _assinatura_adicionais(item: ItemPedido) -> tuple[int | None, ...]:
    """Retorna uma tupla ordenada com os IDs dos adicionais do item para uso como chave de agrupamento."""
    return tuple(sorted(adicional.adicional_id for adicional in item.adicionais))


def _status_grupo(itens: list[ItemPedido]) -> StatusItemPedido:
    """Determina o status consolidado de um grupo de itens da cozinha."""
    if any(item.status == StatusItemPedido.preparando for item in itens):
        return StatusItemPedido.preparando
    return StatusItemPedido.aberto


def listar_cozinha(db: Session, unidade_id: int | None = None) -> list[CozinhaItemRead]:
    """Lista os itens pendentes de preparo agrupados por produto/lote para exibicao na cozinha."""
    query = (
        db.query(ItemPedido)
        .join(ItemPedido.pedido)
        .filter(
            Pedido.status != StatusPedido.cancelado,
            ItemPedido.status.in_([StatusItemPedido.aberto, StatusItemPedido.preparando]),
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
                pedido_id=primeiro.pedido_id,
                nome_comanda=primeiro.pedido.nome_comanda,
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
    return resposta


def atualizar_status_cozinha(db: Session, data: AtualizarStatusCozinha) -> list[ItemPedido]:
    """Atualiza o status de todos os itens de um lote de um pedido na cozinha."""
    if data.status not in {StatusItemPedido.preparando, StatusItemPedido.entregue}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status de cozinha invalido",
        )

    pedido = obter_pedido(db, data.pedido_id)
    _validar_pedido_nao_cancelado(pedido)

    itens = [
        item
        for item in pedido.itens
        if item.lote == data.lote
        and item.status in {StatusItemPedido.aberto, StatusItemPedido.preparando}
    ]
    if not itens:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote de cozinha nao encontrado")

    for item in itens:
        item.status = data.status

    db.commit()
    return itens
