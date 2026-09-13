from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class DuvidaFrequente(Base):
    __tablename__ = "duvidas_frequentes"

    id: Mapped[int] = mapped_column(primary_key=True)
    pergunta: Mapped[str] = mapped_column(String(255), nullable=False)
    resposta: Mapped[str] = mapped_column(Text, nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
