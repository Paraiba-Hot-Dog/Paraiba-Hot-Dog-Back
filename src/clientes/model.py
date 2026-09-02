from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


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
