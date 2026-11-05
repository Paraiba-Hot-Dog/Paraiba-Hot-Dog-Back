import logging
from datetime import UTC, datetime, time, timedelta, timezone, tzinfo
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from src.analytics import ingestao
from src.analytics.model import (
    CanalAquisicao,
    EventoAnalytics,
    TipoEventoAnalytics,
)
from src.analytics.schema import (
    AcaoPorTipoRead,
    AcoesGeradasRead,
    AnalisesAquisicaoRead,
    AquisicaoRead,
    EscopoAquisicao,
    EscoposIndicadoresRead,
    EventoAnalyticsCreate,
    FunilEtapaRead,
    IndicadoresAquisicaoRead,
    OrigemCanalRead,
    PeriodoAquisicao,
    ProdutoVisualizadoRead,
    UnidadeComparacaoRead,
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

LIMITE_PRODUTOS_MAIS_VISUALIZADOS = 10
NOME_PRODUTO_REMOVIDO = "Produto removido"
NOME_SEM_UNIDADE = "Sem unidade ou removida"

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


def _razao(parte: int, total: int) -> Decimal | None:
    if total == 0:
        return None
    return (Decimal(parte) / Decimal(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _filtrar_periodo_e_canal(consulta, inicio: datetime, fim: datetime, canal: CanalAquisicao | None):
    consulta = consulta.where(EventoAnalytics.ocorrido_em >= inicio, EventoAnalytics.ocorrido_em < fim)
    if canal is not None:
        consulta = consulta.where(EventoAnalytics.canal == canal)
    return consulta


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


def _contagens_por_escopo(
    db: Session,
    inicio: datetime,
    fim: datetime,
    unidade_id: int | None,
    canal: CanalAquisicao | None,
) -> tuple[dict[TipoEventoAnalytics, tuple[int, int]], dict[TipoEventoAnalytics, EscopoAquisicao]]:
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
    return contagens, escopos


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
    contagens, escopos = _contagens_por_escopo(db, inicio, fim, unidade_id, canal)

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


def _contagens_por_canal(
    db: Session,
    inicio: datetime,
    fim: datetime,
    unidade_id: int | None,
    canal: CanalAquisicao | None,
) -> dict[CanalAquisicao, tuple[int, int, int]]:
    primeiro = EventoAnalytics.primeiro_na_visita.is_(True)
    visita = EventoAnalytics.tipo == TipoEventoAnalytics.visita_site
    clique = EventoAnalytics.tipo == TipoEventoAnalytics.clique_pedir
    if unidade_id is not None:
        clique = and_(clique, EventoAnalytics.unidade_id == unidade_id)

    consulta = _filtrar_periodo_e_canal(
        select(
            EventoAnalytics.canal,
            func.count().filter(and_(visita, primeiro)),  # pylint: disable=not-callable
            func.count().filter(clique),  # pylint: disable=not-callable
            func.count().filter(and_(clique, primeiro)),  # pylint: disable=not-callable
        ).where(
            EventoAnalytics.tipo.in_(
                (TipoEventoAnalytics.visita_site, TipoEventoAnalytics.clique_pedir)
            )
        ),
        inicio,
        fim,
        canal,
    ).group_by(EventoAnalytics.canal)
    return {
        canal_linha: (visitantes, cliques, visitas_com_clique)
        for canal_linha, visitantes, cliques, visitas_com_clique in db.execute(consulta)
    }


def _origem_por_canal(
    db: Session,
    inicio: datetime,
    fim: datetime,
    unidade_id: int | None,
    canal: CanalAquisicao | None,
) -> list[OrigemCanalRead]:
    contagens = _contagens_por_canal(db, inicio, fim, unidade_id, canal)
    canais = [canal] if canal is not None else list(CanalAquisicao)
    total_visitantes = sum(contagens.get(canal_linha, (0, 0, 0))[0] for canal_linha in canais)
    escopo_cliques = _escopo_da_etapa(TipoEventoAnalytics.clique_pedir, unidade_id)
    escopo_taxa = _escopo_conversao(EscopoAquisicao.site, escopo_cliques)

    origem = []
    for canal_linha in canais:
        visitantes, cliques, visitas_com_clique = contagens.get(canal_linha, (0, 0, 0))
        origem.append(
            OrigemCanalRead(
                canal=canal_linha,
                visitantes=visitantes,
                participacao=_percentual(visitantes, total_visitantes),
                cliques_pedir=cliques,
                escopo_cliques=escopo_cliques,
                taxa_visita_clique=_percentual(visitas_com_clique, visitantes),
                escopo_taxa=escopo_taxa,
            )
        )
    return origem


def _acoes_geradas(
    contagens: dict[TipoEventoAnalytics, tuple[int, int]],
    escopos: dict[TipoEventoAnalytics, EscopoAquisicao],
) -> AcoesGeradasRead:
    total_acoes = sum(contagens[tipo][0] for tipo in ETAPAS_FUNIL)
    so_site = all(escopos[tipo] == EscopoAquisicao.site for tipo in ETAPAS_FUNIL)
    return AcoesGeradasRead(
        total_acoes=total_acoes,
        acoes_por_visita=_razao(total_acoes, contagens[TipoEventoAnalytics.visita_site][1]),
        escopo_acoes_por_visita=(
            EscopoAquisicao.site if so_site else EscopoAquisicao.unidade_sobre_site
        ),
        por_tipo=[
            AcaoPorTipoRead(tipo=tipo, total=contagens[tipo][0], escopo=escopos[tipo])
            for tipo in ETAPAS_FUNIL
        ],
    )


def _produtos_mais_visualizados(
    db: Session,
    inicio: datetime,
    fim: datetime,
    unidade_id: int | None,
    canal: CanalAquisicao | None,
) -> list[ProdutoVisualizadoRead]:
    visualizacoes = func.count().label("visualizacoes")  # pylint: disable=not-callable
    consulta = _filtrar_periodo_e_canal(
        select(EventoAnalytics.produto_id, Produto.nome, visualizacoes)
        .outerjoin(Produto, Produto.id == EventoAnalytics.produto_id)
        .where(EventoAnalytics.tipo == TipoEventoAnalytics.visualizacao_produto),
        inicio,
        fim,
        canal,
    )
    if unidade_id is not None:
        consulta = consulta.where(EventoAnalytics.unidade_id == unidade_id)
    consulta = (
        consulta.group_by(EventoAnalytics.produto_id, Produto.nome)
        .order_by(
            visualizacoes.desc(),
            EventoAnalytics.produto_id.is_(None),
            Produto.nome,
            EventoAnalytics.produto_id,
        )
        .limit(LIMITE_PRODUTOS_MAIS_VISUALIZADOS)
    )

    escopo = _escopo_da_etapa(TipoEventoAnalytics.visualizacao_produto, unidade_id)
    produtos: list[ProdutoVisualizadoRead] = []
    for posicao, (produto_id, nome, total) in enumerate(db.execute(consulta), start=1):
        empatado = bool(produtos) and produtos[-1].visualizacoes == total
        produtos.append(
            ProdutoVisualizadoRead(
                rank=produtos[-1].rank if empatado else posicao,
                produto_id=produto_id,
                nome=nome if produto_id is not None else NOME_PRODUTO_REMOVIDO,
                visualizacoes=total,
                escopo=escopo,
            )
        )
    return produtos


def _comparacao_por_unidade(
    db: Session,
    inicio: datetime,
    fim: datetime,
    unidade_id: int | None,
    canal: CanalAquisicao | None,
) -> list[UnidadeComparacaoRead]:
    primeiro = EventoAnalytics.primeiro_na_visita.is_(True)
    escolha = and_(EventoAnalytics.tipo == TipoEventoAnalytics.selecao_unidade, primeiro)
    clique = EventoAnalytics.tipo == TipoEventoAnalytics.clique_pedir
    escolhas = func.count().filter(escolha).label("escolhas")  # pylint: disable=not-callable

    consulta = _filtrar_periodo_e_canal(
        select(
            EventoAnalytics.unidade_id,
            Unidade.nome,
            escolhas,
            func.count().filter(clique),  # pylint: disable=not-callable
            func.count().filter(and_(clique, primeiro)),  # pylint: disable=not-callable
        )
        .outerjoin(Unidade, Unidade.id == EventoAnalytics.unidade_id)
        .where(
            EventoAnalytics.tipo.in_(
                (TipoEventoAnalytics.selecao_unidade, TipoEventoAnalytics.clique_pedir)
            )
        ),
        inicio,
        fim,
        canal,
    )
    if unidade_id is not None:
        consulta = consulta.where(EventoAnalytics.unidade_id == unidade_id)
    consulta = consulta.group_by(EventoAnalytics.unidade_id, Unidade.nome).order_by(
        escolhas.desc(),
        EventoAnalytics.unidade_id.is_(None),
        Unidade.nome,
        EventoAnalytics.unidade_id,
    )

    linhas = list(db.execute(consulta))
    total_escolhas = sum(linha[2] for linha in linhas)
    return [
        UnidadeComparacaoRead(
            unidade_id=id_unidade,
            nome=nome if id_unidade is not None else NOME_SEM_UNIDADE,
            escolhas=total,
            participacao_escolhas=_percentual(total, total_escolhas),
            cliques_pedir=cliques,
            taxa_escolha_clique=_percentual(visitas_com_clique, total),
        )
        for id_unidade, nome, total, cliques, visitas_com_clique in linhas
    ]


def obter_analises_aquisicao(
    db: Session,
    *,
    periodo: PeriodoAquisicao = PeriodoAquisicao.ultimos_30_dias,
    unidade_id: int | None = None,
    canal: CanalAquisicao | None = None,
    agora: datetime | None = None,
) -> AnalisesAquisicaoRead:
    inicio, fim = intervalo_periodo(periodo, agora)
    contagens, escopos = _contagens_por_escopo(db, inicio, fim, unidade_id, canal)
    return AnalisesAquisicaoRead(
        origem=_origem_por_canal(db, inicio, fim, unidade_id, canal),
        acoes=_acoes_geradas(contagens, escopos),
        produtos=_produtos_mais_visualizados(db, inicio, fim, unidade_id, canal),
        unidades=_comparacao_por_unidade(db, inicio, fim, unidade_id, canal),
    )
