import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.clientes.model import Cliente
from src.database import get_db

PONTOS_PREMIO_FIDELIDADE = 10

router = APIRouter()


class FidelidadeRead(BaseModel):
    id: int
    nome: str
    pontos: int
    total_para_premio: int = PONTOS_PREMIO_FIDELIDADE

    model_config = ConfigDict(from_attributes=True)


def _normalizar_cadastro(cadastro: str) -> tuple[str, str]:
    cadastro_limpo = cadastro.strip()
    telefone = re.sub(r"\D", "", cadastro_limpo)

    return cadastro_limpo, telefone


@router.get("", response_model=FidelidadeRead)
def consultar_fidelidade(
    cadastro: str = Query(..., min_length=3),
    db: Session = Depends(get_db),
) -> FidelidadeRead:
    """Consulta os pontos de fidelidade por telefone ou e-mail cadastrado."""
    cadastro_limpo, telefone = _normalizar_cadastro(cadastro)

    cliente = (
        db.query(Cliente)
        .filter(
            Cliente.ativo.is_(True),
            or_(
                Cliente.email == cadastro_limpo,
                Cliente.telefone == telefone,
            ),
        )
        .first()
    )

    if cliente is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cliente nao encontrado",
        )

    return FidelidadeRead(
        id=cliente.id,
        nome=cliente.nome,
        pontos=cliente.pontos_fidelidade,
        total_para_premio=PONTOS_PREMIO_FIDELIDADE,
    )
