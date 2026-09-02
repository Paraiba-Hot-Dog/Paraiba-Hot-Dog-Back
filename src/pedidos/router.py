from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.pedidos import repository
from src.pedidos.schema import (
    AdicionarItensPedido,
    AumentarQuantidadeItemPedido,
    AtualizarStatusCozinha,
    CancelarItemPedido,
    CancelarPedido,
    CozinhaItemRead,
    FinalizarPedido,
    ItemPedidoRead,
    PedidoCreate,
    PedidoFiltro,
    PedidoRead,
)

router = APIRouter()


@router.post("/", response_model=PedidoRead, status_code=status.HTTP_201_CREATED)
def criar_pedido(data: PedidoCreate, db: Session = Depends(get_db)) -> PedidoRead:
    """Cria um novo pedido com os itens iniciais informados."""
    return repository.criar_pedido(db, data)


@router.get("/", response_model=list[PedidoRead])
def listar_pedidos(
    filtro: PedidoFiltro = Depends(),
    db: Session = Depends(get_db),
) -> list[PedidoRead]:
    """Lista pedidos com filtros opcionais de unidade e status."""
    return repository.listar_pedidos(db, filtro)


@router.get("/cozinha", response_model=list[CozinhaItemRead])
def listar_cozinha(
    unidade_id: int | None = Query(None, gt=0),
    db: Session = Depends(get_db),
) -> list[CozinhaItemRead]:
    """Lista itens pendentes de preparo para exibicao na tela da cozinha."""
    return repository.listar_cozinha(db, unidade_id)


@router.patch("/cozinha/status", response_model=list[ItemPedidoRead])
def atualizar_status_cozinha(
    data: AtualizarStatusCozinha,
    db: Session = Depends(get_db),
) -> list[ItemPedidoRead]:
    """Atualiza o status de preparo de um lote de itens de um pedido na cozinha."""
    return repository.atualizar_status_cozinha(db, data)


@router.get("/{pedido_id}", response_model=PedidoRead)
def obter_pedido(pedido_id: int, db: Session = Depends(get_db)) -> PedidoRead:
    """Retorna os detalhes de um pedido pelo ID."""
    return repository.obter_pedido(db, pedido_id)


@router.post("/{pedido_id}/itens", response_model=PedidoRead)
def adicionar_itens(
    pedido_id: int,
    data: AdicionarItensPedido,
    db: Session = Depends(get_db),
) -> PedidoRead:
    """Adiciona novos itens a um pedido aberto existente."""
    return repository.adicionar_itens(db, pedido_id, data)


@router.post("/itens/{item_id}/cancelar", response_model=PedidoRead)
def cancelar_item(
    item_id: int,
    data: CancelarItemPedido,
    db: Session = Depends(get_db),
) -> PedidoRead:
    """Cancela total ou parcialmente um item do pedido."""
    return repository.cancelar_item(db, item_id, data)


@router.post("/itens/{item_id}/aumentar", response_model=PedidoRead)
def aumentar_quantidade_item(
    item_id: int,
    data: AumentarQuantidadeItemPedido,
    db: Session = Depends(get_db),
) -> PedidoRead:
    """Aumenta a quantidade de um item ainda nao preparado."""
    return repository.aumentar_quantidade_item(db, item_id, data)


@router.post("/{pedido_id}/cancelar", response_model=PedidoRead)
def cancelar_pedido(
    pedido_id: int,
    data: CancelarPedido,
    db: Session = Depends(get_db),
) -> PedidoRead:
    """Cancela um pedido aberto, registrando o motivo do cancelamento."""
    return repository.cancelar_pedido(db, pedido_id, data)


@router.post("/{pedido_id}/finalizar", response_model=PedidoRead)
def finalizar_pedido(
    pedido_id: int,
    data: FinalizarPedido,
    db: Session = Depends(get_db),
) -> PedidoRead:
    """Finaliza e fecha um pedido com a forma de pagamento informada."""
    return repository.finalizar_pedido(db, pedido_id, data)
