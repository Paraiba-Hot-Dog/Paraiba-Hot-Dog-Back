from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.permissoes.model import Permissao
from src.unidades.model import Unidade
from src.auth.supabase_auth import signup as supabase_signup, update_user as supabase_update_user, delete_user as supabase_delete_user
from src.usuarios.model import Usuario
from src.usuarios.schema import UsuarioCreate, UsuarioUpdate


def _resolver_permissoes(db: Session, ids: list[int]) -> list[Permissao]:
    """Busca permissoes pelos IDs informados, lancando 404 se alguma nao for encontrada."""
    permissoes = db.query(Permissao).filter(Permissao.id.in_(ids)).all()
    if len(permissoes) != len(ids):
        raise HTTPException(status_code=404, detail="Uma ou mais permissoes nao encontradas")
    return permissoes


def _validar_unidade(db: Session, unidade_id: int | None) -> None:
    """Valida se a unidade existe no banco, lancando 404 se nao encontrada. Ignora None."""
    if unidade_id is None:
        return
    if not db.get(Unidade, unidade_id):
        raise HTTPException(status_code=404, detail="Unidade nao encontrada")


def _tratar_integridade(e: IntegrityError) -> HTTPException:
    """Mapeia um erro de integridade do banco para a HTTPException adequada."""
    erro = str(e.orig).lower()
    if "email" in erro:
        return HTTPException(status_code=409, detail="Email ja cadastrado")
    if "fk_usuarios_unidade_id" in erro or "usuarios_unidade_id_fkey" in erro:
        return HTTPException(status_code=404, detail="Unidade nao encontrada")
    return HTTPException(status_code=409, detail="Violacao de integridade")


def create_usuario(db: Session, data: UsuarioCreate) -> Usuario:
    """Cria um novo usuario no banco e no Supabase Auth."""
    permissoes = _resolver_permissoes(db, data.permissao_ids)
    _validar_unidade(db, data.unidade_id)

    # Cria usuario no Supabase Auth
    auth_user = supabase_signup(
        email=str(data.email),
        password=data.senha,
        user_metadata={"nome": data.nome, "funcao": data.funcao.value},
    )
    auth_user_id = auth_user.get("id")

    db_usuario = Usuario(
        **data.model_dump(exclude={"permissao_ids", "senha"}),
        auth_provider_id=auth_user_id,
    )
    db_usuario.permissoes = permissoes
    db.add(db_usuario)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        if auth_user_id:
            supabase_delete_user(auth_user_id)
        raise _tratar_integridade(e) from e
    db.refresh(db_usuario)
    return db_usuario


def list_usuarios(db: Session, email: str | None, nome: str | None) -> list[Usuario]:
    """Lista usuarios com filtros opcionais de e-mail e nome, ordenados por ID."""
    query = db.query(Usuario)
    if email:
        query = query.filter(Usuario.email == email)
    if nome:
        query = query.filter(Usuario.nome.ilike(f"%{nome}%"))
    return query.order_by(Usuario.id.asc()).all()


def get_usuario(db: Session, usuario_id: int) -> Usuario:
    """Retorna um usuario pelo ID ou lanca 404 se nao encontrado."""
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    return usuario


def update_usuario(db: Session, usuario_id: int, data: UsuarioUpdate) -> Usuario:
    """Atualiza os campos fornecidos de um usuario e propaga as alteracoes ao Supabase Auth."""
    usuario = get_usuario(db, usuario_id)
    update_data = data.model_dump(exclude_unset=True)
    if "unidade_id" in update_data:
        _validar_unidade(db, update_data["unidade_id"])
    if "permissao_ids" in update_data:
        usuario.permissoes = _resolver_permissoes(db, update_data.pop("permissao_ids"))

    # Prepara atualizacao no Supabase Auth
    supabase_email = str(update_data["email"]) if "email" in update_data else None
    supabase_senha = update_data.pop("senha", None)

    for field, value in update_data.items():
        setattr(usuario, field, value)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise _tratar_integridade(e) from e
    db.refresh(usuario)

    # Sincroniza com Supabase Auth
    supabase_update_user(usuario.auth_provider_id, email=supabase_email, password=supabase_senha)
    return usuario


def delete_usuario(db: Session, usuario_id: int) -> None:
    """Remove um usuario do banco de dados e do Supabase Auth."""
    usuario = get_usuario(db, usuario_id)
    auth_user_id = usuario.auth_provider_id
    db.delete(usuario)
    db.commit()
    supabase_delete_user(auth_user_id)
