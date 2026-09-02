from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from src.blog.model import TipoNoticiaPromocao


class BlogBase(BaseModel):
    titulo: str = Field(..., max_length=255)
    imagem_url: Optional[str] = Field(None, max_length=500)
    descricao: Optional[str] = None
    tipo: TipoNoticiaPromocao
    data: date


class BlogCreate(BlogBase):
    pass


class BlogMultipartCreate(BaseModel):
    titulo: str = Field(..., max_length=255)
    tipo: TipoNoticiaPromocao
    data: date
    imagem: bytes = Field(..., json_schema_extra={"format": "binary"})
    descricao: Optional[str] = None


class BlogUpdate(BaseModel):
    titulo: Optional[str] = Field(None, max_length=255)
    imagem_url: Optional[str] = Field(None, max_length=500)
    descricao: Optional[str] = None
    tipo: Optional[TipoNoticiaPromocao] = None
    data: Optional[date] = None


class BlogRead(BlogBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
