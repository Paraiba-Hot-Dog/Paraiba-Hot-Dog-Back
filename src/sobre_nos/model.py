from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class SobreNosImagem(Base):
    __tablename__ = "sobre_nos_imagens"

    id: Mapped[int] = mapped_column(primary_key=True)
    imagem_url: Mapped[str] = mapped_column(String(500), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    posicao: Mapped[str | None] = mapped_column(String(50), nullable=True)
