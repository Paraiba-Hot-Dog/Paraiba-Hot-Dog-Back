from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.permissoes import repository
from src.permissoes.schema import PermissaoRead, PermissaoUpdate

router = APIRouter()


@router.get("/", response_model=list[PermissaoRead])
def listar_permissoes(db: Session = Depends(get_db)):
    """Retorna todas as permissoes cadastradas."""
    return repository.listar_permissoes(db)


@router.get("/{permissao_id}", response_model=PermissaoRead)
def obter_permissao(permissao_id: int, db: Session = Depends(get_db)):
    """Retorna uma permissao pelo ID."""
    return repository.obter_permissao(db, permissao_id)


@router.post("/{permissao_id}/conceder/{usuario_id}", response_model=PermissaoRead)
def conceder_permissao(permissao_id: int, usuario_id: int, db: Session = Depends(get_db)):
    """Concede a permissao especificada ao usuario informado."""
    return repository.conceder_permissao(db, permissao_id, usuario_id)


@router.patch("/{permissao_id}", response_model=PermissaoRead)
def atualizar_permissao(permissao_id: int, data: PermissaoUpdate, db: Session = Depends(get_db)):
    """Atualiza o nome de uma permissao existente."""
    return repository.atualizar_permissao(db, permissao_id, data)


@router.delete("/{permissao_id}/revogar/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def revogar_permissao(permissao_id: int, usuario_id: int, db: Session = Depends(get_db)):
    """Revoga a permissao especificada do usuario informado."""
    repository.revogar_permissao(db, permissao_id, usuario_id)
