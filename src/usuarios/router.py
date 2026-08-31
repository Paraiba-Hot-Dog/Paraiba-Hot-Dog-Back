from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from src.database import get_db
from src.usuarios import repository
from src.usuarios.schema import UsuarioCreate, UsuarioRead, UsuarioUpdate

router = APIRouter()


@router.post("/", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
def create_usuario(usuario_create: UsuarioCreate, db: Session = Depends(get_db)) -> UsuarioRead:
    """Cria um novo usuario e o sincroniza com o Supabase Auth."""
    return UsuarioRead.model_validate(repository.create_usuario(db, usuario_create))


@router.get("/", response_model=list[UsuarioRead])
def list_usuarios(
    email: str | None = Query(default=None),
    nome: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[UsuarioRead]:
    """Lista usuarios com filtros opcionais de e-mail e nome."""
    return [UsuarioRead.model_validate(u) for u in repository.list_usuarios(db, email, nome)]


@router.get("/{usuario_id}", response_model=UsuarioRead)
def get_usuario(usuario_id: int, db: Session = Depends(get_db)) -> UsuarioRead:
    """Retorna os dados de um usuario pelo ID."""
    return UsuarioRead.model_validate(repository.get_usuario(db, usuario_id))


@router.patch("/{usuario_id}", response_model=UsuarioRead)
def update_usuario(usuario_id: int, data: UsuarioUpdate, db: Session = Depends(get_db)) -> UsuarioRead:
    """Atualiza parcialmente os dados de um usuario existente."""
    return UsuarioRead.model_validate(repository.update_usuario(db, usuario_id, data))


@router.delete("/{usuario_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_usuario(usuario_id: int, db: Session = Depends(get_db)) -> Response:
    """Remove um usuario pelo ID e o exclui do Supabase Auth."""
    repository.delete_usuario(db, usuario_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
