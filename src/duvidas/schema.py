from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

PerguntaStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
]
RespostaStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DuvidaBase(BaseModel):
    pergunta: PerguntaStr
    resposta: RespostaStr
    ordem: int = Field(0, ge=0)
    ativo: bool = True


class DuvidaCreate(DuvidaBase):
    pass


class DuvidaUpdate(BaseModel):
    pergunta: Optional[PerguntaStr] = None
    resposta: Optional[RespostaStr] = None
    ordem: Optional[int] = Field(None, ge=0)
    ativo: Optional[bool] = None


class DuvidaRead(DuvidaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
