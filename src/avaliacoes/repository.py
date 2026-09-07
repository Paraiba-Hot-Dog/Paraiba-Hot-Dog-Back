from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.avaliacoes.model import Avaliacao
from src.avaliacoes.schema import AvaliacaoCreate, AvaliacaoUpdate


def listar_avaliacoes(
    db: Session,
    ativo: bool | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Avaliacao]:
    """Lista as avaliacoes com paginacao e filtro opcional por status de exibicao."""
    query = db.query(Avaliacao)
    if ativo is not None:
        query = query.filter(Avaliacao.ativo.is_(ativo))
    return query.order_by(Avaliacao.id.desc()).offset(skip).limit(limit).all()


def obter_avaliacao(db: Session, avaliacao_id: int) -> Avaliacao:
    """Retorna uma avaliacao pelo ID ou lanca 404 se nao encontrada."""
    avaliacao = db.get(Avaliacao, avaliacao_id)
    if not avaliacao:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Avaliacao nao encontrada",
        )
    return avaliacao


def criar_avaliacao(db: Session, data: AvaliacaoCreate) -> Avaliacao:
    """Persiste uma nova avaliacao cadastrada pelo administrador."""
    avaliacao = Avaliacao(**data.model_dump())
    db.add(avaliacao)
    db.commit()
    db.refresh(avaliacao)
    return avaliacao


def atualizar_avaliacao(
    db: Session, avaliacao_id: int, data: AvaliacaoUpdate
) -> Avaliacao:
    """Altera a visibilidade de uma avaliacao (exibida ou oculta no site)."""
    avaliacao = obter_avaliacao(db, avaliacao_id)
    avaliacao.ativo = data.ativo
    db.commit()
    db.refresh(avaliacao)
    return avaliacao


def excluir_avaliacao(db: Session, avaliacao_id: int) -> None:
    """Remove permanentemente uma avaliacao."""
    avaliacao = obter_avaliacao(db, avaliacao_id)
    db.delete(avaliacao)
    db.commit()
