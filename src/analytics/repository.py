import logging
from datetime import UTC, datetime, time, timedelta, timezone, tzinfo
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.analytics import ingestao
from src.analytics.model import (
    CanalAquisicao,
    EventoAnalytics,
    TipoEventoAnalytics,
)
from src.analytics.schema import (
    AquisicaoRead,
    EscopoAquisicao,
    EscoposIndicadoresRead,
    EventoAnalyticsCreate,
    FunilEtapaRead,
    IndicadoresAquisicaoRead,
    PeriodoAquisicao,
)
from src.produtos.model import Produto
from src.unidades.model import Unidade

logger = logging.getLogger(__name__)

ETAPAS_FUNIL = (
    TipoEventoAnalytics.visita_site,
    TipoEventoAnalytics.abertura_cardapio,
    TipoEventoAnalytics.selecao_unidade,
    TipoEventoAnalytics.visualizacao_produto,
    TipoEventoAnalytics.clique_pedir,
)

# Etapas que acontecem antes de a visita escolher unidade. Com filtro de
# unidade, contam o site inteiro.
ETAPAS_SEM_UNIDADE = frozenset(
    {TipoEventoAnalytics.visita_site, TipoEventoAnalytics.abertura_cardapio}
)

DIAS_POR_PERIODO = {
    PeriodoAquisicao.ultimos_7_dias: 7,
    PeriodoAquisicao.ultimos_30_dias: 30,
    PeriodoAquisicao.ultimos_90_dias: 90,
}


def _fuso_sao_paulo() -> tzinfo:
    """Fuso de Brasilia; sem base de fusos no sistema, usa UTC-3 fixo (sem horario de verao desde 2019)."""
    try:
        return ZoneInfo("America/Sao_Paulo")
    except ZoneInfoNotFoundError:
        logger.warning(
            "analytics: base de fusos indisponivel, usando UTC-3 fixo para America/Sao_Paulo"
        )
        return timezone(timedelta(hours=-3), "America/Sao_Paulo")


FUSO_SAO_PAULO = _fuso_sao_paulo()


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
        versao_coleta=data.versao_coleta,
    )
    db.add(evento)
    db.commit()
    return evento


def intervalo_periodo(
    periodo: PeriodoAquisicao,
    agora: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Limites [inicio, fim) em UTC sem fuso, calculados por dia de Brasilia.

    "Ultimos N dias" inclui o dia atual: comeca a meia-noite de N-1 dias
    atras e termina a meia-noite de amanha, no horario de Brasilia.
    """
    momento = agora or datetime.now(UTC)
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    hoje = momento.astimezone(FUSO_SAO_PAULO).date()

    inicio_local = datetime.combine(
        hoje - timedelta(days=DIAS_POR_PERIODO[periodo] - 1), time.min, FUSO_SAO_PAULO
    )
    fim_local = datetime.combine(hoje + timedelta(days=1), time.min, FUSO_SAO_PAULO)

    def _utc(valor: datetime) -> datetime:
        return valor.astimezone(UTC).replace(tzinfo=None)

    return _utc(inicio_local), _utc(fim_local)


def _percentual(parte: int, total: int) -> Decimal | None:
    if total == 0:
        return None
    return (Decimal(parte) * Decimal("100") / Decimal(total)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _contagens_por_tipo(
    db: Session,
    inicio: datetime,
    fim: datetime,
    unidade_id: int | None,
    canal: CanalAquisicao | None,
) -> dict[TipoEventoAnalytics, tuple[int, int]]:
    """Retorna, por tipo, (total de eventos, eventos com primeiro_na_visita)."""
    consulta = (
        select(
            EventoAnalytics.tipo,
            func.count(),  # pylint: disable=not-callable
            func.count().filter(EventoAnalytics.primeiro_na_visita.is_(True)),  # pylint: disable=not-callable
        )
        .where(EventoAnalytics.ocorrido_em >= inicio, EventoAnalytics.ocorrido_em < fim)
        .group_by(EventoAnalytics.tipo)
    )
    if unidade_id is not None:
        consulta = consulta.where(EventoAnalytics.unidade_id == unidade_id)
    if canal is not None:
        consulta = consulta.where(EventoAnalytics.canal == canal)

    return {tipo: (total, primeiros) for tipo, total, primeiros in db.execute(consulta)}


def _escopo_da_etapa(tipo: TipoEventoAnalytics, unidade_id: int | None) -> EscopoAquisicao:
    if unidade_id is None or tipo in ETAPAS_SEM_UNIDADE:
        return EscopoAquisicao.site
    return EscopoAquisicao.unidade


def _escopo_conversao(
    escopo_anterior: EscopoAquisicao,
    escopo_atual: EscopoAquisicao,
) -> EscopoAquisicao:
    if escopo_anterior == escopo_atual:
        return escopo_atual
    return EscopoAquisicao.unidade_sobre_site


def _montar_funil(
    volumes: list[int],
    escopos: list[EscopoAquisicao],
) -> list[FunilEtapaRead]:
    """Monta as etapas com conversao, perda e maior abandono.

    A passagem do site para a unidade (escopo misto) nao concorre a maior
    abandono, porque a perda inclui quem escolheu outra unidade.
    """
    etapas: list[FunilEtapaRead] = []
    maior_perda_relativa = Decimal("0")
    indice_maior_abandono: int | None = None

    for indice, (etapa, volume, escopo) in enumerate(zip(ETAPAS_FUNIL, volumes, escopos)):
        if indice == 0:
            etapas.append(
                FunilEtapaRead(
                    etapa=etapa,
                    volume=volume,
                    escopo=escopo,
                    conversao_etapa_anterior=None,
                    escopo_conversao=None,
                    perda=0,
                    maior_abandono=False,
                )
            )
            continue

        anterior = volumes[indice - 1]
        perda = anterior - volume
        escopo_conversao = _escopo_conversao(escopos[indice - 1], escopo)
        if perda > 0 and escopo_conversao != EscopoAquisicao.unidade_sobre_site:
            perda_relativa = Decimal(perda) / Decimal(anterior)
            if perda_relativa > maior_perda_relativa:
                maior_perda_relativa = perda_relativa
                indice_maior_abandono = indice

        etapas.append(
            FunilEtapaRead(
                etapa=etapa,
                volume=volume,
                escopo=escopo,
                conversao_etapa_anterior=_percentual(volume, anterior),
                escopo_conversao=escopo_conversao,
                perda=perda,
                maior_abandono=False,
            )
        )

    if indice_maior_abandono is not None:
        etapas[indice_maior_abandono].maior_abandono = True
    return etapas


def obter_aquisicao(
    db: Session,
    *,
    periodo: PeriodoAquisicao = PeriodoAquisicao.ultimos_30_dias,
    unidade_id: int | None = None,
    canal: CanalAquisicao | None = None,
    agora: datetime | None = None,
) -> AquisicaoRead:
    """Agrega funil e indicadores de aquisicao em consultas SQL agregadas.

    Com filtro de unidade, as etapas anteriores a escolha da unidade
    (ETAPAS_SEM_UNIDADE) contam o site inteiro, porque esses eventos
    acontecem antes de a visita ter unidade. As demais contam so a unidade.
    Cada numero informa o seu escopo.
    """
    inicio, fim = intervalo_periodo(periodo, agora)
    contagens_unidade = _contagens_por_tipo(db, inicio, fim, unidade_id, canal)
    contagens_site = (
        contagens_unidade
        if unidade_id is None
        else _contagens_por_tipo(db, inicio, fim, None, canal)
    )
    escopos = {tipo: _escopo_da_etapa(tipo, unidade_id) for tipo in ETAPAS_FUNIL}
    contagens = {
        tipo: (contagens_site if escopos[tipo] == EscopoAquisicao.site else contagens_unidade).get(
            tipo, (0, 0)
        )
        for tipo in ETAPAS_FUNIL
    }

    visita = TipoEventoAnalytics.visita_site
    clique = TipoEventoAnalytics.clique_pedir
    visitantes = contagens[visita][1]
    return AquisicaoRead(
        funil=_montar_funil(
            [contagens[etapa][1] for etapa in ETAPAS_FUNIL],
            [escopos[etapa] for etapa in ETAPAS_FUNIL],
        ),
        indicadores=IndicadoresAquisicaoRead(
            visitantes=visitantes,
            visualizacoes_cardapio=contagens[TipoEventoAnalytics.abertura_cardapio][0],
            produtos_visualizados=contagens[TipoEventoAnalytics.visualizacao_produto][0],
            cliques_pedir=contagens[clique][0],
            taxa_visita_clique=_percentual(contagens[clique][1], visitantes),
            escopos=EscoposIndicadoresRead(
                visitantes=escopos[visita],
                visualizacoes_cardapio=escopos[TipoEventoAnalytics.abertura_cardapio],
                produtos_visualizados=escopos[TipoEventoAnalytics.visualizacao_produto],
                cliques_pedir=escopos[clique],
                taxa_visita_clique=_escopo_conversao(escopos[visita], escopos[clique]),
            ),
        ),
    )
