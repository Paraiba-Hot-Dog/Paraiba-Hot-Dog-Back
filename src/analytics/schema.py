from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, StrictBool, StrictInt

from src.analytics.model import (
    VERSAO_COLETA_MAXIMA,
    VERSAO_COLETA_MINIMA,
    TipoEventoAnalytics,
)


class EventoAnalyticsCreate(BaseModel):
    """Payload enviado pelo site publico.

    UTMs e referrer chegam brutos: a normalizacao e o descarte de valores
    fora do formato acontecem na ingestao, sem rejeitar o evento. O front
    nao envia horario nem identificador de visita.
    """

    tipo: TipoEventoAnalytics
    primeiro_na_visita: StrictBool
    # Versao das regras de disparo do front que gerou o evento.
    versao_coleta: StrictInt = Field(ge=VERSAO_COLETA_MINIMA, le=VERSAO_COLETA_MAXIMA)
    unidade_id: int | None = None
    produto_id: int | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    referrer_host: str | None = None


class PeriodoAquisicao(str, Enum):
    ultimos_7_dias = "ultimos_7_dias"
    ultimos_30_dias = "ultimos_30_dias"
    ultimos_90_dias = "ultimos_90_dias"


class EscopoAquisicao(str, Enum):
    """De onde vem um numero quando ha filtro de unidade.

    - site: todo o site (sem filtro de unidade, tudo e `site`).
    - unidade: so a unidade filtrada.
    - unidade_sobre_site: taxa que divide um numero da unidade por um do site.
    """

    site = "site"
    unidade = "unidade"
    unidade_sobre_site = "unidade_sobre_site"


class FunilEtapaRead(BaseModel):
    etapa: TipoEventoAnalytics
    volume: int
    escopo: EscopoAquisicao
    # Percentual (ex.: 42.50). None na primeira etapa ou se a anterior for zero.
    # Pode passar de 100, porque as etapas sao contadas de forma independente.
    conversao_etapa_anterior: Decimal | None
    # Escopo da conversao e da perda; None na primeira etapa.
    escopo_conversao: EscopoAquisicao | None
    # Pode ser negativa quando a etapa tem mais visitas que a anterior.
    perda: int
    maior_abandono: bool


class EscoposIndicadoresRead(BaseModel):
    visitantes: EscopoAquisicao
    visualizacoes_cardapio: EscopoAquisicao
    produtos_visualizados: EscopoAquisicao
    cliques_pedir: EscopoAquisicao
    taxa_visita_clique: EscopoAquisicao


class IndicadoresAquisicaoRead(BaseModel):
    visitantes: int
    visualizacoes_cardapio: int
    produtos_visualizados: int
    cliques_pedir: int
    # Percentual (ex.: 12.34). None quando nao houve visitas.
    taxa_visita_clique: Decimal | None
    escopos: EscoposIndicadoresRead


class AquisicaoRead(BaseModel):
    funil: list[FunilEtapaRead]
    indicadores: IndicadoresAquisicaoRead
