from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AvaliacaoBase(BaseModel):
    cliente_id: int = Field(..., gt=0)
    unidade_id: int = Field(..., gt=0)
    descricao: str = Field(..., min_length=1)
    estrelas: int = Field(..., ge=1, le=5)


class AvaliacaoCreate(AvaliacaoBase):
    pass


class AvaliacaoUpdate(BaseModel):
    cliente_id: Optional[int] = Field(None, gt=0)
    unidade_id: Optional[int] = Field(None, gt=0)
    descricao: Optional[str] = Field(None, min_length=1)
    estrelas: Optional[int] = Field(None, ge=1, le=5)


class AvaliacaoRead(BaseModel):
    id: int
    cliente_id: int
    unidade_id: int
    nome_cliente: str
    nome_unidade: str
    descricao: str
    estrelas: int

    model_config = ConfigDict(from_attributes=True)
