"""Modelos SQLAlchemy para Sobre Nos e carrossel de imagens."""

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class SobreNos(Base):
    """Modelo do texto institucional e cards de estatisticas da pagina Sobre Nos."""

    __tablename__ = "sobre_nos"

    id: Mapped[int] = mapped_column(primary_key=True)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    estatisticas: Mapped[list] = mapped_column(JSON, nullable=False)


class SobreNosImagem(Base):
    """Modelo das imagens e videos do carrossel da pagina Sobre Nos."""

    __tablename__ = "sobre_nos_imagens"

    id: Mapped[int] = mapped_column(primary_key=True)
    imagem_url: Mapped[str] = mapped_column(String(500), nullable=False)
    ordem: Mapped[int] = mapped_column(default=0, nullable=False)
    posicao: Mapped[str | None] = mapped_column(String(50), nullable=True)
