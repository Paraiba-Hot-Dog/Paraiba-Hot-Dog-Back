from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class SobreNos(Base):
    __tablename__ = "sobre_nos"

    id: Mapped[int] = mapped_column(primary_key=True)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
