from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analytics import ingestao
from src.analytics.model import VERSAO_COLETA_ATUAL, EventoAnalytics
from src.analytics.schema import EventoAnalyticsCreate
from src.produtos.model import Produto
from src.unidades.model import Unidade


def _id_existente(db: Session, modelo, valor: int | None, campo: str) -> int | None:
    """Mantem o id apenas se o registro existir; caso contrario descarta o campo."""
    if valor is None:
        return None
    if valor > 0 and db.scalar(select(modelo.id).where(modelo.id == valor)) is not None:
        return valor
    ingestao.registrar_contador(f"campo_descartado campo={campo}")
    return None


def registrar_evento(db: Session, data: EventoAnalyticsCreate) -> EventoAnalytics:
    """Normaliza o payload, calcula o canal e grava o evento com horario truncado."""
    utm_source = ingestao.normalizar_utm(data.utm_source, "utm_source")
    referrer_host = ingestao.normalizar_referrer_host(data.referrer_host)

    evento = EventoAnalytics(
        tipo=data.tipo,
        primeiro_na_visita=data.primeiro_na_visita,
        unidade_id=_id_existente(db, Unidade, data.unidade_id, "unidade_id"),
        produto_id=_id_existente(db, Produto, data.produto_id, "produto_id"),
        canal=ingestao.calcular_canal(utm_source, referrer_host),
        utm_source=utm_source,
        utm_medium=ingestao.normalizar_utm(data.utm_medium, "utm_medium"),
        utm_campaign=ingestao.normalizar_utm(data.utm_campaign, "utm_campaign"),
        referrer_host=referrer_host,
        ocorrido_em=ingestao.horario_truncado_utc(),
        versao_coleta=VERSAO_COLETA_ATUAL,
    )
    db.add(evento)
    db.commit()
    return evento
