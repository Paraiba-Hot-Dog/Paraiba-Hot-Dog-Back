from datetime import date
from enum import Enum

from sqlalchemy import Date, Enum as SQLEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class TipoNoticiaPromocao(str, Enum):
    noticia = "noticia"
    promocao = "promocao"


class Blog(Base):
    __tablename__ = "noticias_promocoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    imagem_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo: Mapped[TipoNoticiaPromocao] = mapped_column(
        SQLEnum(TipoNoticiaPromocao, name="tipo_noticia_promocao"),
        nullable=False,
    )
    data: Mapped[date] = mapped_column(Date, nullable=False)
