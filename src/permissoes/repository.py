from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.permissoes.model import Permissao, TipoPermissao
from src.permissoes.schema import PermissaoUpdate
from src.usuarios.model import Usuario


def listar_permissoes(db: Session) -> list[Permissao]:
    """Retorna todas as permissoes cadastradas no sistema."""
    return db.query(Permissao).all()


def obter_permissao(db: Session, permissao_id: int) -> Permissao:
    """Retorna uma permissao pelo ID ou lanca 404 se nao encontrada."""
    permissao = db.get(Permissao, permissao_id)
    if not permissao:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permissao nao encontrada")
    return permissao


def criar_permissao(db: Session, nome: TipoPermissao) -> Permissao:
    """Cria uma nova permissao no banco de dados, lancando 409 se ja existir."""
    permissao = Permissao(nome=nome)
    db.add(permissao)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Permissao ja cadastrada") from exc
    db.refresh(permissao)
    return permissao


def atualizar_permissao(db: Session, permissao_id: int, data: PermissaoUpdate) -> Permissao:
    """Atualiza o nome de uma permissao existente."""
    permissao = obter_permissao(db, permissao_id)
    permissao.nome = data.nome
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Permissao ja cadastrada") from exc
    db.refresh(permissao)
    return permissao


def excluir_permissao(db: Session, permissao_id: int) -> None:
    """Remove permanentemente uma permissao do banco de dados."""
    permissao = obter_permissao(db, permissao_id)
    db.delete(permissao)
    db.commit()


def conceder_permissao(db: Session, permissao_id: int, usuario_id: int) -> Permissao:
    """Associa uma permissao a um usuario, lancando 409 se ele ja a possuir."""
    permissao = obter_permissao(db, permissao_id)
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado")
    if permissao in usuario.permissoes:
        raise HTTPException(status_code=409, detail="Usuario ja possui essa permissao")
    usuario.permissoes.append(permissao)
    db.commit()
    db.refresh(permissao)
    return permissao


def revogar_permissao(db: Session, permissao_id: int, usuario_id: int) -> None:
    """Remove a associacao de uma permissao de um usuario, lancando 404 se ele nao a possuir."""
    permissao = obter_permissao(db, permissao_id)
    usuario = db.get(Usuario, usuario_id)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado")
    if permissao not in usuario.permissoes:
        raise HTTPException(status_code=404, detail="Usuario nao possui essa permissao")
    usuario.permissoes.remove(permissao)
    db.commit()
