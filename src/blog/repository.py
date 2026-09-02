from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.blog.model import Blog
from src.blog.schema import BlogCreate, BlogUpdate


def listar_posts(db: Session, tipo: str | None = None, skip: int = 0, limit: int = 100) -> list[Blog]:
    """Lista as postagens do blog com paginacao e filtro opcional por tipo."""
    query = db.query(Blog)
    if tipo:
        query = query.filter(Blog.tipo == tipo)
    return query.offset(skip).limit(limit).all()


def obter_post(db: Session, post_id: int) -> Blog:
    """Retorna uma postagem pelo ID ou lanca 404 se nao encontrada."""
    post = db.get(Blog, post_id)
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Postagem nao encontrada")
    return post


def criar_post(db: Session, data: BlogCreate) -> Blog:
    """Persiste uma nova postagem no banco de dados e a retorna."""
    post = Blog(**data.model_dump())
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


def atualizar_post(db: Session, post_id: int, data: BlogUpdate) -> Blog:
    """Atualiza os campos fornecidos de uma postagem existente e a retorna atualizada."""
    post = obter_post(db, post_id)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(post, field, value)
    db.commit()
    db.refresh(post)
    return post


def excluir_post(db: Session, post_id: int) -> None:
    """Remove permanentemente uma postagem do banco de dados."""
    post = obter_post(db, post_id)
    db.delete(post)
    db.commit()
