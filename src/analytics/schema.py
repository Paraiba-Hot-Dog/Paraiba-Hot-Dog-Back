from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, StrictBool

from src.analytics.model import TipoEventoAnalytics


class EventoAnalyticsCreate(BaseModel):
    """Payload enviado pelo site publico.

    UTMs e referrer chegam brutos: a normalizacao e o descarte de valores
    fora do formato acontecem na ingestao, sem rejeitar o evento. O front
    nao envia horario nem identificador de visita.
    """

    tipo: TipoEventoAnalytics
    primeiro_na_visita: StrictBool
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


class FunilEtapaRead(BaseModel):
    etapa: TipoEventoAnalytics
    volume: int
    # Percentual (ex.: 42.50). None na primeira etapa ou se a anterior for zero.
    # Pode passar de 100, porque as etapas sao contadas de forma independente.
    conversao_etapa_anterior: Decimal | None
    # Pode ser negativa quando a etapa tem mais visitas que a anterior.
    perda: int
    maior_abandono: bool


class IndicadoresAquisicaoRead(BaseModel):
    visitantes: int
    visualizacoes_cardapio: int
    produtos_visualizados: int
    cliques_pedir: int
    # Percentual (ex.: 12.34). None quando nao houve visitas.
    taxa_visita_clique: Decimal | None


class AquisicaoRead(BaseModel):
    funil: list[FunilEtapaRead]
    indicadores: IndicadoresAquisicaoRead
