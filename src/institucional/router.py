from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.institucional import repository
from src.institucional.schema import SobreNosRead, SobreNosUpdate
from src.security import get_current_user

router = APIRouter()


@router.get("/sobre-nos", response_model=SobreNosRead)
def obter_sobre_nos(db: Session = Depends(get_db)):
    return repository.obter_sobre_nos(db)


@router.put(
    "/sobre-nos",
    response_model=SobreNosRead,
    dependencies=[Depends(get_current_user)],
)
def atualizar_sobre_nos(data: SobreNosUpdate, db: Session = Depends(get_db)):
    return repository.atualizar_sobre_nos(db, data)
