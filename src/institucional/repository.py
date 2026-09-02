from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.institucional.model import SobreNos
from src.institucional.schema import SobreNosUpdate


def obter_sobre_nos(db: Session) -> SobreNos:
    conteudo = db.get(SobreNos, 1)
    if not conteudo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conteudo de Sobre Nos nao encontrado",
        )
    return conteudo


def atualizar_sobre_nos(db: Session, data: SobreNosUpdate) -> SobreNos:
    conteudo = obter_sobre_nos(db)
    conteudo.texto = data.texto
    db.commit()
    db.refresh(conteudo)
    return conteudo
