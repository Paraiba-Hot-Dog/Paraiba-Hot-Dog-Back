from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.duvidas import repository
from src.duvidas.schema import DuvidaCreate, DuvidaRead, DuvidaUpdate
from src.security import require_roles

router = APIRouter()


@router.get("/", response_model=list[DuvidaRead])
def listar_duvidas(
    apenas_ativas: bool = True,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Lista as duvidas frequentes ordenadas por ordem de exibicao."""
    return repository.listar_duvidas(db, apenas_ativas, skip, limit)


@router.get("/{duvida_id}", response_model=DuvidaRead)
def obter_duvida(duvida_id: int, db: Session = Depends(get_db)):
    """Retorna uma duvida frequente pelo ID."""
    return repository.obter_duvida(db, duvida_id)


@router.post(
    "/",
    response_model=DuvidaRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles("administrador"))],
)
def criar_duvida(data: DuvidaCreate, db: Session = Depends(get_db)):
    """Cria uma nova duvida frequente. Requer role administrador."""
    return repository.criar_duvida(db, data)


@router.patch(
    "/{duvida_id}",
    response_model=DuvidaRead,
    dependencies=[Depends(require_roles("administrador"))],
)
def atualizar_duvida(duvida_id: int, data: DuvidaUpdate, db: Session = Depends(get_db)):
    """Atualiza parcialmente uma duvida frequente existente. Requer role administrador."""
    return repository.atualizar_duvida(db, duvida_id, data)


@router.delete(
    "/{duvida_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_roles("administrador"))],
)
def excluir_duvida(duvida_id: int, db: Session = Depends(get_db)):
    """Remove uma duvida frequente pelo ID. Requer role administrador."""
    repository.excluir_duvida(db, duvida_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
