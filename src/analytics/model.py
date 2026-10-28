from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base

# A versao da coleta vem do front (VERSAO_COLETA em src/servicos/analyticsApi.ts),
# ao lado das regras de disparo. Limites aceitos na ingestao:
VERSAO_COLETA_MINIMA = 1
VERSAO_COLETA_MAXIMA = 100


class TipoEventoAnalytics(str, Enum):
    visita_site = "visita_site"
    abertura_cardapio = "abertura_cardapio"
    selecao_unidade = "selecao_unidade"
    visualizacao_produto = "visualizacao_produto"
    clique_pedir = "clique_pedir"


class CanalAquisicao(str, Enum):
    instagram = "instagram"
    qrcode = "qrcode"
    campanha_outros = "campanha_outros"
    busca = "busca"
    outros_sites = "outros_sites"
    direto = "direto"


class EventoAnalytics(Base):
    """Evento de navegacao anonimizado do site publico.

    Nao guarda nenhum identificador de visita, dispositivo ou pessoa.
    """

    __tablename__ = "eventos_analytics"
    __table_args__ = (
        Index("ix_eventos_analytics_tipo_ocorrido_em", "tipo", "ocorrido_em"),
        Index("ix_eventos_analytics_ocorrido_em", "ocorrido_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[TipoEventoAnalytics] = mapped_column(
        SQLEnum(TipoEventoAnalytics, name="tipo_evento_analytics"),
        nullable=False,
    )
    primeiro_na_visita: Mapped[bool] = mapped_column(Boolean, nullable=False)
    unidade_id: Mapped[int | None] = mapped_column(
        ForeignKey("unidades.id", ondelete="SET NULL"),
        nullable=True,
    )
    produto_id: Mapped[int | None] = mapped_column(
        ForeignKey("produtos.id", ondelete="SET NULL"),
        nullable=True,
    )
    canal: Mapped[CanalAquisicao] = mapped_column(
        SQLEnum(CanalAquisicao, name="canal_aquisicao"),
        nullable=False,
    )
    utm_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(100), nullable=True)
    referrer_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Horario em UTC (sem fuso), truncado para a hora pelo servidor.
    ocorrido_em: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    versao_coleta: Mapped[int] = mapped_column(SmallInteger, nullable=False)
