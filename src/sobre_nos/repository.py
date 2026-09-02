from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.sobre_nos.model import SobreNosImagem
from src.sobre_nos.schema import SobreNosImagemCreate, SobreNosImagemUpdate


def listar_imagens(db: Session) -> list[SobreNosImagem]:
    """Lista as imagens do carrossel ordenadas pelo campo ordem."""
    return db.query(SobreNosImagem).order_by(SobreNosImagem.ordem).all()


def obter_imagem(db: Session, imagem_id: int) -> SobreNosImagem:
    """Retorna uma imagem pelo ID ou lanca 404 se nao encontrada."""
    imagem = db.get(SobreNosImagem, imagem_id)
    if not imagem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Imagem nao encontrada")
    return imagem


def criar_imagem(db: Session, data: SobreNosImagemCreate) -> SobreNosImagem:
    """Persiste uma nova imagem do carrossel e a retorna."""
    if data.ordem == 0:
        maior_ordem = db.query(SobreNosImagem).count()
        data = data.model_copy(update={"ordem": maior_ordem})

    imagem = SobreNosImagem(**data.model_dump())
    db.add(imagem)
    db.commit()
    db.refresh(imagem)
    return imagem


def atualizar_imagem(db: Session, imagem_id: int, data: SobreNosImagemUpdate) -> SobreNosImagem:
    """Atualiza os campos fornecidos de uma imagem existente e a retorna atualizada."""
    imagem = obter_imagem(db, imagem_id)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(imagem, field, value)
    db.commit()
    db.refresh(imagem)
    return imagem


def excluir_imagem(db: Session, imagem_id: int) -> None:
    """Remove permanentemente uma imagem do carrossel."""
    imagem = obter_imagem(db, imagem_id)
    db.delete(imagem)
    db.commit()
