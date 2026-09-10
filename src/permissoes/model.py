from enum import Enum

from sqlalchemy import Column, Enum as SQLEnum, ForeignKey, Integer, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

usuario_permissoes = Table(
    "usuario_permissoes",
    Base.metadata,
    Column("usuario_id", Integer, ForeignKey("usuarios.id"), primary_key=True),
    Column("permissao_id", Integer, ForeignKey("permissoes.id"), primary_key=True),
)


class TipoPermissao(str, Enum):
    anotar_pedidos = "anotar_pedidos"
    cozinha = "cozinha"
    dashboard = "dashboard"
    configuracoes = "configuracoes"


class Permissao(Base):
    __tablename__ = "permissoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[TipoPermissao] = mapped_column(
        SQLEnum(TipoPermissao, name="tipo_permissao"),
        nullable=False,
        unique=True,
    )
    usuarios: Mapped[list["Usuario"]] = relationship(secondary=usuario_permissoes, back_populates="permissoes")
