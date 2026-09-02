import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.clientes import repository
from src.clientes.repository import _mapear_erro_integridade
from src.clientes.schema import ClienteCreate, ClienteFiltro, ClienteRead, ClienteUpdate
from src.database import get_db
from src.whatsapp.whatsapp_boas_vindas import enviar_boas_vindas

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=ClienteRead, status_code=status.HTTP_201_CREATED)
def criar_cliente(
    data: ClienteCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> ClienteRead:
    """Cadastra um novo cliente e agenda o envio de mensagem de boas-vindas via WhatsApp."""
    try:
        cliente = repository.criar_cliente(db, data)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=_mapear_erro_integridade(e)) from e
    background_tasks.add_task(enviar_boas_vindas, cliente.nome, cliente.telefone)
    logger.info(
        "Cliente cadastrado com sucesso (id=%s). Envio de WhatsApp agendado.",
        cliente.id,
    )
    return ClienteRead.model_validate(cliente)


@router.get("/", response_model=list[ClienteRead])
def listar_clientes(
    filtro: ClienteFiltro = Depends(),
    db: Session = Depends(get_db),
) -> list[ClienteRead]:
    """Lista os clientes ativos de acordo com os filtros informados."""
    clientes = repository.listar_clientes(db, filtro)
    return [ClienteRead.model_validate(c) for c in clientes]


@router.get("/{cliente_id}", response_model=ClienteRead)
def obter_cliente(cliente_id: int, db: Session = Depends(get_db)) -> ClienteRead:
    """Retorna os dados de um cliente ativo pelo ID."""
    cliente = repository.obter_cliente(db, cliente_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return ClienteRead.model_validate(cliente)


@router.patch("/{cliente_id}", response_model=ClienteRead)
def atualizar_cliente(cliente_id: int, data: ClienteUpdate, db: Session = Depends(get_db)) -> ClienteRead:
    """Atualiza parcialmente os dados de um cliente existente."""
    try:
        cliente = repository.atualizar_cliente(db, cliente_id, data)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=_mapear_erro_integridade(e)) from e
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return ClienteRead.model_validate(cliente)


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def excluir_cliente(cliente_id: int, db: Session = Depends(get_db)) -> Response:
    """Realiza a exclusao logica de um cliente pelo ID."""
    deleted = repository.excluir_cliente(db, cliente_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
