from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.bi import repository
from src.bi.schema import BiDashboardRead
from src.database import get_db

router = APIRouter()

@router.get("/dashboard", response_model=BiDashboardRead)
def obter_dashboard(
    unidade_id: int | None = Query(None, gt=0),
    ano: int | None = Query(None, ge=2000),
    mes: int | None = Query(None, ge=1, le=12),
    fechamento_mes: bool = Query(False),
    db: Session = Depends(get_db),
) -> BiDashboardRead:
    """Retorna os indicadores agregados da tela de BI."""
    return repository.obter_dashboard(db, unidade_id, ano, mes, fechamento_mes)
