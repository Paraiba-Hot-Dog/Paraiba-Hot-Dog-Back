from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.unidades.model import Endereco, Unidade
from src.unidades.schema import UnidadeCreate, UnidadeUpdate


def listar_unidades(db: Session) -> list[Unidade]:
    """Retorna todas as unidades cadastradas."""
    return db.query(Unidade).all()


def obter_unidade(db: Session, unidade_id: int) -> Unidade:
    """Retorna uma unidade pelo ID ou lanca 404 se nao encontrada."""
    unidade = db.get(Unidade, unidade_id)
    if not unidade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unidade nao encontrada")
    return unidade


def criar_unidade(db: Session, data: UnidadeCreate) -> Unidade:
    """Cria uma nova unidade com seu endereco associado."""
    endereco = Endereco(**data.endereco.model_dump())
    db.add(endereco)
    db.flush()
    unidade = Unidade(**data.model_dump(exclude={"endereco"}), endereco_id=endereco.id)
    db.add(unidade)
    db.commit()
    db.refresh(unidade)
    return unidade


def atualizar_unidade(db: Session, unidade_id: int, data: UnidadeUpdate) -> Unidade:
    """Atualiza os campos fornecidos de uma unidade, incluindo seu endereco se necessario."""
    unidade = obter_unidade(db, unidade_id)
    update_data = data.model_dump(exclude_unset=True)
    endereco_data = update_data.pop("endereco", None)

    for field, value in update_data.items():
        setattr(unidade, field, value)

    if endereco_data is not None:
        if unidade.endereco is None:
            endereco = Endereco(**endereco_data)
            db.add(endereco)
            db.flush()
            unidade.endereco_id = endereco.id
        else:
            for field, value in endereco_data.items():
                setattr(unidade.endereco, field, value)

    db.commit()
    db.refresh(unidade)
    return unidade


def excluir_unidade(db: Session, unidade_id: int) -> str | None:
    """Remove permanentemente uma unidade, seu endereco associado e retorna a url da imagem."""
    unidade = obter_unidade(db, unidade_id)
    imagem_url = unidade.imagem
    endereco_id = unidade.endereco_id

    db.delete(unidade)
    db.flush()

    if endereco_id is not None:
        endereco = db.get(Endereco, endereco_id)
        if endereco is not None:
            db.delete(endereco)

    db.commit()
    return imagem_url
