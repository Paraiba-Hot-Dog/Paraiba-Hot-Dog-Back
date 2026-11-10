from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.unidades.model import Unidade


produto_unidades = Table(
    "produto_unidades",
    Base.metadata,
    Column("produto_id", ForeignKey("produtos.id"), primary_key=True),
    Column("unidade_id", ForeignKey("unidades.id"), primary_key=True),
)

produto_grupos_opcoes = Table(
    "produto_grupos_opcoes",
    Base.metadata,
    Column("produto_id", ForeignKey("produtos.id", ondelete="CASCADE"), primary_key=True),
    Column("grupo_id", ForeignKey("grupos_opcoes.id", ondelete="CASCADE"), primary_key=True),
    Column("ordem", Integer, default=0, nullable=False),
)


class Categoria(Base):
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(primary_key=True)

    nome: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    subcategorias: Mapped[list[Subcategoria]] = relationship(
        "Subcategoria",
        back_populates="categoria",
        cascade="all, delete-orphan",
    )


class Subcategoria(Base):
    __tablename__ = "subcategorias"

    id: Mapped[int] = mapped_column(primary_key=True)

    nome: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    categoria_id: Mapped[int] = mapped_column(
        ForeignKey("categorias.id"),
        nullable=False,
    )

    categoria: Mapped[Categoria] = relationship(
        "Categoria",
        back_populates="subcategorias",
        lazy="joined",
    )

    produtos: Mapped[list[Produto]] = relationship(
        "Produto",
        back_populates="subcategoria",
        cascade="all, delete-orphan",
    )


class Produto(Base):
    __tablename__ = "produtos"

    id: Mapped[int] = mapped_column(primary_key=True)

    nome: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
    )

    descricao: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    imagem_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    ativo: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    pontos_fidelidade_por_unidade: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    disponivel_todas_unidades: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    disponivel_no_combo: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    valor_adicional_combo: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False,
    )

    subcategoria_id: Mapped[int] = mapped_column(
        ForeignKey("subcategorias.id"),
        nullable=False,
    )

    subcategoria: Mapped[Subcategoria] = relationship(
        "Subcategoria",
        back_populates="produtos",
        lazy="joined",
    )

    variacoes: Mapped[list[ProdutoVariacao]] = relationship(
        "ProdutoVariacao",
        back_populates="produto",
        cascade="all, delete-orphan",
    )

    unidades: Mapped[list[Unidade]] = relationship(
        "Unidade",
        secondary=produto_unidades,
        lazy="selectin",
    )

    grupos: Mapped[list[GrupoOpcao]] = relationship(
        "GrupoOpcao",
        secondary=produto_grupos_opcoes,
        back_populates="produtos",
        lazy="selectin",
    )

    @property
    def adicionais(self) -> list[dict]:
        """Compatibilidade legada: extrai opcoes do grupo de adicionais."""
        for grupo in self.grupos:
            nome_baixo = grupo.nome.lower()
            if "adicion" in nome_baixo or "acrésc" in nome_baixo or "acresc" in nome_baixo:
                return [
                    {
                        "id": op.id,
                        "produto_id": self.id,
                        "nome": op.nome,
                        "preco": op.preco,
                    }
                    for op in grupo.opcoes
                    if op.ativo
                ]
        return []

    @property
    def disponivel_combo(self) -> bool:
        """Alias para compatibilidade com clientes que esperam disponivel_combo."""
        return self.disponivel_no_combo

    @property
    def unidade_ids(self) -> list[int]:
        """Retorna a lista de IDs das unidades onde o produto esta disponivel."""
        return [unidade.id for unidade in self.unidades]


class TipoVariacao(str, Enum):
    normal = "normal"
    combo = "combo"


class ProdutoVariacao(Base):
    __tablename__ = "produto_variacoes"

    id: Mapped[int] = mapped_column(primary_key=True)

    produto_id: Mapped[int] = mapped_column(
        ForeignKey("produtos.id"),
        nullable=False,
    )

    nome: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )

    tipo: Mapped[TipoVariacao] = mapped_column(
        SQLEnum(TipoVariacao, name="tipo_variacao"),
        nullable=False,
    )

    preco: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    ativo: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    produto: Mapped[Produto] = relationship(
        "Produto",
        back_populates="variacoes",
        lazy="joined",
    )


class ProdutoAdicional:
    """Fabrica de compatibilidade legada que instancia OpcaoComplemento."""
    def __new__(cls, *args, **kwargs):
        kwargs.pop("produto_id", None)
        if "grupo_id" not in kwargs:
            kwargs["grupo_id"] = 1
        return OpcaoComplemento(*args, **kwargs)


class GrupoOpcao(Base):
    __tablename__ = "grupos_opcoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    obrigatorio: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    minimo: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    maximo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    opcoes: Mapped[list[OpcaoComplemento]] = relationship(
        "OpcaoComplemento",
        back_populates="grupo",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    produtos: Mapped[list[Produto]] = relationship(
        "Produto",
        secondary=produto_grupos_opcoes,
        back_populates="grupos",
        lazy="selectin",
    )


class OpcaoComplemento(Base):
    __tablename__ = "opcoes_complemento"

    id: Mapped[int] = mapped_column(primary_key=True)
    grupo_id: Mapped[int] = mapped_column(
        ForeignKey("grupos_opcoes.id", ondelete="CASCADE"),
        nullable=False,
    )
    nome: Mapped[str] = mapped_column(String(100), nullable=False)
    preco: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    grupo: Mapped[GrupoOpcao] = relationship(
        "GrupoOpcao",
        back_populates="opcoes",
        lazy="joined",
    )
