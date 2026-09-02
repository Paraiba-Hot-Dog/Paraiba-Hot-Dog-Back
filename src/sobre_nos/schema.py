from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SobreNosImagemBase(BaseModel):
    imagem_url: str = Field(..., max_length=500)
    ordem: int = 0
    posicao: Optional[str] = Field(None, max_length=50)


class SobreNosImagemCreate(SobreNosImagemBase):
    pass


class SobreNosImagemUpdate(BaseModel):
    ordem: Optional[int] = None
    posicao: Optional[str] = Field(None, max_length=50)


class SobreNosImagemRead(SobreNosImagemBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
