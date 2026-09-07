from pydantic import BaseModel, ConfigDict, Field


class AvaliacaoBase(BaseModel):
    nome_cliente: str = Field(..., min_length=1, max_length=120)
    descricao: str = Field(..., min_length=1)
    estrelas: int = Field(..., ge=1, le=5)


class AvaliacaoCreate(AvaliacaoBase):
    pass


class AvaliacaoUpdate(BaseModel):
    ativo: bool


class AvaliacaoRead(AvaliacaoBase):
    id: int
    ativo: bool

    model_config = ConfigDict(from_attributes=True)
