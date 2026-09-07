from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.avaliacoes import repository
from src.avaliacoes.schema import AvaliacaoCreate, AvaliacaoRead
from src.database import get_db

router = APIRouter()


@router.post(
    "/clientes/{cliente_id}/unidades/{unidade_id}",
    response_model=AvaliacaoRead,
    status_code=status.HTTP_201_CREATED,
)
def criar_avaliacao(
    cliente_id: int,
    unidade_id: int,
    data: AvaliacaoCreate,
    db: Session = Depends(get_db),
) -> AvaliacaoRead:
    """Cria uma avaliacao vinculada a um cliente e a uma unidade."""
    try:
        return repository.criar_avaliacao(db, cliente_id, unidade_id, data)
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nao foi possivel registrar a avaliacao",
        ) from e
