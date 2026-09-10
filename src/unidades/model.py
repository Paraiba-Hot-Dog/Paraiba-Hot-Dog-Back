from datetime import time

from sqlalchemy import ForeignKey, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Endereco(Base):
    __tablename__ = "enderecos"

    id: Mapped[int] = mapped_column(primary_key=True)
    cep: Mapped[str] = mapped_column(String(8), nullable=False)
    logradouro: Mapped[str] = mapped_column(String(255), nullable=False)
    numero: Mapped[str | None] = mapped_column(String(10), nullable=True)
    complemento: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bairro: Mapped[str] = mapped_column(String(255), nullable=False)
    cidade: Mapped[str] = mapped_column(String(255), nullable=False)
    estado: Mapped[str] = mapped_column(String(2), nullable=False)


class Unidade(Base):
    __tablename__ = "unidades"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    imagem: Mapped[str | None] = mapped_column(String(500), nullable=True)
    abertura: Mapped[time] = mapped_column(Time, nullable=False)
    fechamento: Mapped[time] = mapped_column(Time, nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    mapa_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    endereco_id: Mapped[int] = mapped_column(ForeignKey("enderecos.id"), nullable=True)

    endereco: Mapped[Endereco] = relationship("Endereco", lazy="joined")
