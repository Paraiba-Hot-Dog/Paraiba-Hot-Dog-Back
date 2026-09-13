from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.duvidas.model import DuvidaFrequente
from src.duvidas.schema import DuvidaCreate, DuvidaUpdate


def listar_duvidas(
    db: Session,
    apenas_ativas: bool = True,
    skip: int = 0,
    limit: int = 100,
) -> list[DuvidaFrequente]:
    """Lista as duvidas frequentes ordenadas, com paginacao e filtro opcional por ativas."""
    query = db.query(DuvidaFrequente)
    if apenas_ativas:
        query = query.filter(DuvidaFrequente.ativo.is_(True))
    query = query.order_by(DuvidaFrequente.ordem, DuvidaFrequente.id)
    return query.offset(skip).limit(limit).all()


def obter_duvida(db: Session, duvida_id: int) -> DuvidaFrequente:
    """Retorna uma duvida frequente pelo ID ou lanca 404 se nao encontrada."""
    duvida = db.get(DuvidaFrequente, duvida_id)
    if not duvida:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Duvida nao encontrada")
    return duvida


def criar_duvida(db: Session, data: DuvidaCreate) -> DuvidaFrequente:
    """Persiste uma nova duvida frequente no banco de dados e a retorna."""
    duvida = DuvidaFrequente(**data.model_dump())
    db.add(duvida)
    db.commit()
    db.refresh(duvida)
    return duvida


def atualizar_duvida(db: Session, duvida_id: int, data: DuvidaUpdate) -> DuvidaFrequente:
    """Atualiza os campos fornecidos de uma duvida existente e a retorna atualizada."""
    duvida = obter_duvida(db, duvida_id)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(duvida, field, value)
    db.commit()
    db.refresh(duvida)
    return duvida


def excluir_duvida(db: Session, duvida_id: int) -> None:
    """Remove permanentemente uma duvida frequente do banco de dados."""
    duvida = obter_duvida(db, duvida_id)
    db.delete(duvida)
    db.commit()
