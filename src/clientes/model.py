from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base
from src.usuarios.model import Usuario


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    telefone: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(
        String(120), unique=True, nullable=True)
    pontos_fidelidade: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    data_cadastro: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False  # pylint: disable=not-callable
    )


class MotivoAjustePontos(Base):
    """Motivos predefinidos para ajustes manuais no saldo de fidelidade."""

    __tablename__ = "motivos_ajuste_pontos"

    id: Mapped[int] = mapped_column(primary_key=True)
    descricao: Mapped[str] = mapped_column(
        String(120), unique=True, nullable=False)
    exige_observacao: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ClienteAjustePontos(Base):
    """Registro de auditoria de cada ajuste manual no saldo de fidelidade."""

    __tablename__ = "clientes_ajustes_pontos"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clientes.id"), nullable=False, index=True)
    motivo_id: Mapped[int] = mapped_column(
        ForeignKey("motivos_ajuste_pontos.id"), nullable=False)
    observacao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pontos_anterior: Mapped[int] = mapped_column(Integer, nullable=False)
    pontos_atual: Mapped[int] = mapped_column(Integer, nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True)
    data_ajuste: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False  # pylint: disable=not-callable
    )

    motivo: Mapped[MotivoAjustePontos] = relationship()
    usuario: Mapped[Usuario | None] = relationship()

    @property
    def usuario_nome(self) -> str | None:
        """Nome do usuario que realizou o ajuste, se identificado."""
        return self.usuario.nome if self.usuario else None
