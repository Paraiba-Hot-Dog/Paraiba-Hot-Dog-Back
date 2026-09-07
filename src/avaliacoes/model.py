from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base

if TYPE_CHECKING:
    from src.clientes.model import Cliente
    from src.unidades.model import Unidade


class Avaliacao(Base):
    __tablename__ = "avaliacoes"
    __table_args__ = (
        CheckConstraint(
            "estrelas BETWEEN 1 AND 5", name="ck_avaliacoes_estrelas_1_5"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clientes.id"), nullable=False, index=True
    )
    unidade_id: Mapped[int] = mapped_column(
        ForeignKey("unidades.id", ondelete="CASCADE"), nullable=False, index=True
    )
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    estrelas: Mapped[int] = mapped_column(Integer, nullable=False)

    cliente: Mapped[Cliente] = relationship("Cliente", lazy="joined")
    unidade: Mapped[Unidade] = relationship("Unidade", lazy="joined")

    @property
    def nome_cliente(self) -> str:
        """Nome do cliente que fez a avaliacao."""
        return self.cliente.nome

    @property
    def nome_unidade(self) -> str:
        """Nome da unidade avaliada."""
        return self.unidade.nome
