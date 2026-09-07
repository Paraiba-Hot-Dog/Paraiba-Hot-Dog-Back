from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from src.avaliacoes import repository
from src.avaliacoes.schema import AvaliacaoCreate, AvaliacaoRead, AvaliacaoUpdate
from src.database import get_db
from src.security import get_current_user

router = APIRouter()


@router.get("", response_model=list[AvaliacaoRead])
def listar_avaliacoes(
    ativo: bool = True,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """Lista as avaliacoes; por padrao apenas as exibidas no site (ativo=true)."""
    return repository.listar_avaliacoes(db, ativo, skip, limit)


@router.post(
    "",
    response_model=AvaliacaoRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(get_current_user)],
)
def criar_avaliacao(data: AvaliacaoCreate, db: Session = Depends(get_db)):
    """Cadastra uma nova avaliacao. Requer autenticacao."""
    return repository.criar_avaliacao(db, data)


@router.patch(
    "/{avaliacao_id}",
    response_model=AvaliacaoRead,
    dependencies=[Depends(get_current_user)],
)
def atualizar_avaliacao(
    avaliacao_id: int,
    data: AvaliacaoUpdate,
    db: Session = Depends(get_db),
):
    """Exibe ou oculta uma avaliacao no site. Requer autenticacao."""
    return repository.atualizar_avaliacao(db, avaliacao_id, data)


@router.delete(
    "/{avaliacao_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(get_current_user)],
)
def excluir_avaliacao(avaliacao_id: int, db: Session = Depends(get_db)):
    """Remove uma avaliacao permanentemente. Requer autenticacao."""
    repository.excluir_avaliacao(db, avaliacao_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
