from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.institucional import repository
from src.institucional.schema import SobreNosRead, SobreNosUpdate
from src.security import require_roles

router = APIRouter()


@router.get("/sobre-nos", response_model=SobreNosRead)
def obter_sobre_nos(db: Session = Depends(get_db)):
    """Retorna o texto e os cards publicos de Sobre Nos. Nao exige autenticacao."""
    return repository.obter_sobre_nos(db)


@router.put(
    "/sobre-nos",
    response_model=SobreNosRead,
    dependencies=[Depends(require_roles("administrador"))],
)
def atualizar_sobre_nos(data: SobreNosUpdate, db: Session = Depends(get_db)):
    """Atualiza o texto e os cards de Sobre Nos. Requer role administrador."""
    return repository.atualizar_sobre_nos(db, data)
