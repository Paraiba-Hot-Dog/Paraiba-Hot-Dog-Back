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
