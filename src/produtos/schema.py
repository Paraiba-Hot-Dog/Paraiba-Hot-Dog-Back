from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from src.produtos.model import TipoVariacao

class CategoriaBase(BaseModel):
    nome: str = Field(..., max_length=100)


class CategoriaCreate(CategoriaBase):
    pass


class CategoriaUpdate(BaseModel):
    nome: Optional[str] = Field(None, max_length=100)


class CategoriaRead(CategoriaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class SubcategoriaBase(BaseModel):
    nome: str = Field(..., max_length=100)

    categoria_id: int = Field(
        ...,
        gt=0,
    )


class SubcategoriaCreate(SubcategoriaBase):
    pass


class SubcategoriaUpdate(BaseModel):
    nome: Optional[str] = Field(
        None,
        max_length=100,
    )

    categoria_id: Optional[int] = Field(
        None,
        gt=0,
    )


class SubcategoriaRead(SubcategoriaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class SubcategoriaReadComCategoria(SubcategoriaRead):
    categoria: CategoriaRead


class ProdutoBase(BaseModel):
    nome: str = Field(
        ...,
        max_length=255,
    )

    descricao: Optional[str] = None

    imagem_url: Optional[str] = Field(
        None,
        max_length=500,
    )

    ativo: bool = True

    pontos_fidelidade_por_unidade: int = Field(default=0, ge=0)

    disponivel_todas_unidades: bool = True

    subcategoria_id: int = Field(
        ...,
        gt=0,
    )


class ProdutoCreate(ProdutoBase):
    unidade_ids: list[int] = []


class ProdutoMultipartCreate(BaseModel):
    nome: str = Field(
        ...,
        max_length=255,
    )

    subcategoria_id: int = Field(
        ...,
        gt=0,
    )

    imagem: bytes = Field(..., json_schema_extra={"format": "binary"})

    descricao: Optional[str] = None

    ativo: bool = True

    pontos_fidelidade_por_unidade: int = Field(default=0, ge=0)

    disponivel_todas_unidades: bool = True

    unidade_ids: list[int] = []


class ProdutoUpdate(BaseModel):
    nome: Optional[str] = Field(
        None,
        max_length=255,
    )

    descricao: Optional[str] = None

    imagem_url: Optional[str] = Field(
        None,
        max_length=500,
    )

    ativo: Optional[bool] = None

    pontos_fidelidade_por_unidade: Optional[int] = Field(None, ge=0)

    disponivel_todas_unidades: Optional[bool] = None

    unidade_ids: Optional[list[int]] = None

    subcategoria_id: Optional[int] = Field(
        None,
        gt=0,
    )


class ProdutoVariacaoBase(BaseModel):
    produto_id: int = Field(
        ...,
        gt=0,
    )

    nome: str = Field(
        ...,
        max_length=80,
    )

    tipo: TipoVariacao

    preco: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
    )

    ativo: bool = True


class ProdutoVariacaoCreate(ProdutoVariacaoBase):
    pass


class ProdutoVariacaoUpdate(BaseModel):
    nome: Optional[str] = Field(
        None,
        max_length=80,
    )

    tipo: Optional[TipoVariacao] = None

    preco: Optional[Decimal] = Field(
        None,
        gt=0,
        decimal_places=2,
    )

    ativo: Optional[bool] = None


class ProdutoVariacaoRead(ProdutoVariacaoBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

class ProdutoAdicionalBase(BaseModel):
    produto_id: int = Field(
        ...,
        gt=0,
    )

    nome: str = Field(
        ...,
        max_length=255,
    )

    preco: Decimal = Field(
        ...,
        gt=0,
        decimal_places=2,
    )


class ProdutoAdicionalCreate(ProdutoAdicionalBase):
    pass


class ProdutoAdicionalUpdate(BaseModel):
    nome: Optional[str] = Field(
        None,
        max_length=255,
    )

    preco: Optional[Decimal] = Field(
        None,
        gt=0,
        decimal_places=2,
    )


class ProdutoAdicionalRead(ProdutoAdicionalBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

class ProdutoRead(ProdutoBase):
    id: int

    unidade_ids: list[int] = []

    variacoes: list[ProdutoVariacaoRead] = []

    adicionais: list[ProdutoAdicionalRead] = []

    model_config = ConfigDict(from_attributes=True)
