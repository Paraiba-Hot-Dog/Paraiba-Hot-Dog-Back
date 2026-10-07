from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.bi import repository
from src.bi.schema import BiDashboardRead
from src.database import get_db

router = APIRouter()

@router.get("/dashboard", response_model=BiDashboardRead)
def obter_dashboard(
    *,
    unidade_id: int | None = Query(None, gt=0),
    ano: int | None = Query(None, ge=2000),
    mes: int | None = Query(None, ge=1, le=12),
    fechamento_mes: bool = Query(False),
    data_inicio: date | None = Query(None),
    data_fim: date | None = Query(None),
    db: Session = Depends(get_db),
) -> BiDashboardRead:
    """Retorna os indicadores agregados da tela de BI."""
    if (data_inicio is None) != (data_fim is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Informe data_inicio e data_fim juntas.",
        )
    if data_inicio is not None and data_fim is not None and data_inicio > data_fim:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="data_inicio nao pode ser posterior a data_fim.",
        )

    return repository.obter_dashboard(
        db,
        unidade_id=unidade_id,
        ano=ano,
        mes=mes,
        fechamento_mes=fechamento_mes,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )
