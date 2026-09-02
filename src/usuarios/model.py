from enum import Enum

from sqlalchemy import Enum as SQLEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base
from src.permissoes.model import Permissao, usuario_permissoes


class FuncaoUsuario(str, Enum):
    administrador = "administrador"
    caixa = "caixa"
    cozinha = "cozinha"


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    auth_provider_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    senha: Mapped[str | None] = mapped_column(String(255), nullable=True)
    funcao: Mapped[FuncaoUsuario] = mapped_column(
        SQLEnum(FuncaoUsuario, name="funcao_usuario"),
        nullable=False,
        default=FuncaoUsuario.caixa,
    )
    unidade_id: Mapped[int | None] = mapped_column(ForeignKey("unidades.id"), nullable=True)

    permissoes: Mapped[list[Permissao]] = relationship(secondary=usuario_permissoes, back_populates="usuarios")
