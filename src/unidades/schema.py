from datetime import time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EnderecoBase(BaseModel):
    cep: str = Field(..., max_length=8)
    logradouro: str = Field(..., max_length=255)
    numero: Optional[str] = Field(None, max_length=10)
    complemento: Optional[str] = Field(None, max_length=255)
    bairro: str = Field(..., max_length=255)
    cidade: str = Field(..., max_length=255)
    estado: str = Field(..., max_length=2)


class EnderecoCreate(EnderecoBase):
    pass


class EnderecoUpdate(BaseModel):
    cep: Optional[str] = Field(None, max_length=8)
    logradouro: Optional[str] = Field(None, max_length=255)
    numero: Optional[str] = Field(None, max_length=10)
    complemento: Optional[str] = Field(None, max_length=255)
    bairro: Optional[str] = Field(None, max_length=255)
    cidade: Optional[str] = Field(None, max_length=255)
    estado: Optional[str] = Field(None, max_length=2)


class EnderecoRead(EnderecoBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class UnidadeBase(BaseModel):
    nome: str = Field(..., max_length=255)
    imagem: Optional[str] = Field(None, max_length=500)
    abertura: time
    fechamento: time
    descricao: Optional[str] = None
    mapa_url: Optional[str] = Field(None, max_length=500)


class UnidadeCreate(UnidadeBase):
    endereco: EnderecoCreate


class UnidadeMultipartCreate(BaseModel):
    nome: str = Field(..., max_length=255)
    abertura: time
    fechamento: time
    cep: str = Field(..., max_length=8)
    logradouro: str = Field(..., max_length=255)
    bairro: str = Field(..., max_length=255)
    cidade: str = Field(..., max_length=255)
    estado: str = Field(..., max_length=2)
    imagem: bytes = Field(..., json_schema_extra={"format": "binary"})
    numero: Optional[str] = Field(None, max_length=10)
    complemento: Optional[str] = Field(None, max_length=255)
    descricao: Optional[str] = None
    mapa_url: Optional[str] = Field(None, max_length=500)


class UnidadeMultipartUpdate(BaseModel):
    nome: Optional[str] = Field(None, max_length=255)
    abertura: Optional[time] = None
    fechamento: Optional[time] = None
    descricao: Optional[str] = None
    mapa_url: Optional[str] = Field(None, max_length=500)
    imagem: Optional[bytes] = Field(None, json_schema_extra={"format": "binary"})
    cep: Optional[str] = Field(None, max_length=8)
    logradouro: Optional[str] = Field(None, max_length=255)
    numero: Optional[str] = Field(None, max_length=10)
    complemento: Optional[str] = Field(None, max_length=255)
    bairro: Optional[str] = Field(None, max_length=255)
    cidade: Optional[str] = Field(None, max_length=255)
    estado: Optional[str] = Field(None, max_length=2)


class UnidadeUpdate(BaseModel):
    nome: Optional[str] = Field(None, max_length=255)
    imagem: Optional[str] = Field(None, max_length=500)
    abertura: Optional[time] = None
    fechamento: Optional[time] = None
    descricao: Optional[str] = None
    mapa_url: Optional[str] = Field(None, max_length=500)
    endereco: Optional[EnderecoUpdate] = None


class UnidadeRead(UnidadeBase):
    id: int
    endereco: EnderecoRead

    model_config = ConfigDict(from_attributes=True)
