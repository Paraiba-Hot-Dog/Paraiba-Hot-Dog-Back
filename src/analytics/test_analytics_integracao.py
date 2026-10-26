import logging
from datetime import UTC, datetime, time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.analytics import ingestao, repository
from src.analytics.model import (
    VERSAO_COLETA_ATUAL,
    CanalAquisicao,
    EventoAnalytics,
    TipoEventoAnalytics,
)
from src.analytics.schema import PeriodoAquisicao
from src.database import Base, get_db
from src.main import app
from src.produtos.model import Categoria, Produto, Subcategoria
from src.security import get_current_user
from src.unidades.model import Endereco, Unidade

TEST_DATABASE_URL = "sqlite+pysqlite:///:memory:"
ORIGEM_SITE = "https://site.paraiba.test"
USER_AGENT_NAVEGADOR = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
CABECALHOS_SITE = {"Origin": ORIGEM_SITE, "User-Agent": USER_AGENT_NAVEGADOR}

# 26/10/2026 18:00 UTC = 15:00 em Brasilia.
AGORA = datetime(2026, 10, 26, 18, 0, tzinfo=UTC)

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(name="db_session", scope="function")
def fixture_db_session():
    """Cria uma sessao SQLite isolada para os testes de analytics."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def override_get_db(db_session):
    """Substitui a dependencia de banco pela sessao de teste."""

    def _get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def configurar_origem_site(monkeypatch):
    """Fixa a origem aceita pela ingestao, independente do .env local."""
    monkeypatch.setattr(ingestao.settings, "frontend_base_url", ORIGEM_SITE)


@pytest.fixture(name="cliente")
def fixture_cliente():
    """Cria o TestClient usado nos cenarios de analytics."""
    return TestClient(app)


@pytest.fixture(name="unidade")
def fixture_unidade(db_session):
    """Cria uma unidade para os eventos que referenciam unidade."""
    unidade = Unidade(
        nome="Unidade Analytics",
        abertura=time(16, 30),
        fechamento=time(23, 59),
        descricao="Unidade teste",
        endereco=Endereco(
            cep="71900000",
            logradouro="Aguas Claras",
            numero="1",
            bairro="Aguas Claras",
            cidade="Brasilia",
            estado="DF",
        ),
    )
    db_session.add(unidade)
    db_session.commit()
    return unidade


@pytest.fixture(name="produto")
def fixture_produto(db_session):
    """Cria um produto para os eventos de visualizacao."""
    categoria = Categoria(nome="Hot-Dog")
    produto = Produto(
        nome="Paraiba Monster XL",
        ativo=True,
        pontos_fidelidade_por_unidade=1,
        disponivel_todas_unidades=True,
        subcategoria=Subcategoria(nome="Lanches", categoria=categoria),
    )
    db_session.add(produto)
    db_session.commit()
    return produto


def _enviar(cliente, payload, cabecalhos=None):
    return cliente.post(
        "/analytics/eventos",
        json=payload,
        headers=CABECALHOS_SITE if cabecalhos is None else cabecalhos,
    )


def _eventos(db_session) -> list[EventoAnalytics]:
    return list(db_session.scalars(select(EventoAnalytics).order_by(EventoAnalytics.id)))


def _criar_eventos(
    db_session,
    tipo: TipoEventoAnalytics,
    quantidade: int = 1,
    *,
    primeiro: bool = True,
    ocorrido_em: datetime = datetime(2026, 10, 26, 12),
    canal: CanalAquisicao = CanalAquisicao.direto,
    unidade_id: int | None = None,
):
    for _ in range(quantidade):
        db_session.add(
            EventoAnalytics(
                tipo=tipo,
                primeiro_na_visita=primeiro,
                canal=canal,
                unidade_id=unidade_id,
                ocorrido_em=ocorrido_em,
                versao_coleta=VERSAO_COLETA_ATUAL,
            )
        )
    db_session.commit()


def _etapas(resultado) -> dict[TipoEventoAnalytics, object]:
    return {etapa.etapa: etapa for etapa in resultado.funil}


# ---------------------------------------------------------------- ingestao


def test_ingestao_grava_evento_valido(cliente, db_session, unidade, produto):
    """Evento valido e gravado com UTMs normalizadas, canal calculado e ids validos."""
    resposta = _enviar(
        cliente,
        {
            "tipo": "visualizacao_produto",
            "primeiro_na_visita": True,
            "unidade_id": unidade.id,
            "produto_id": produto.id,
            "utm_source": "  Instagram ",
            "utm_medium": "Social",
            "utm_campaign": "bio",
            "referrer_host": "L.Instagram.com",
        },
    )

    assert resposta.status_code == 204
    assert resposta.content == b""
    [evento] = _eventos(db_session)
    assert evento.tipo == TipoEventoAnalytics.visualizacao_produto
    assert evento.primeiro_na_visita is True
    assert evento.unidade_id == unidade.id
    assert evento.produto_id == produto.id
    assert evento.canal == CanalAquisicao.instagram
    assert (evento.utm_source, evento.utm_medium, evento.utm_campaign) == (
        "instagram",
        "social",
        "bio",
    )
    assert evento.referrer_host == "l.instagram.com"
    assert evento.versao_coleta == VERSAO_COLETA_ATUAL


@pytest.mark.parametrize(
    "payload",
    [
        {"tipo": "compra_confirmada", "primeiro_na_visita": True},
        {"primeiro_na_visita": True},
        {"tipo": "visita_site"},
        {"tipo": "visita_site", "primeiro_na_visita": "sim"},
        {"tipo": "visita_site", "primeiro_na_visita": True, "unidade_id": "abc"},
        [{"tipo": "visita_site", "primeiro_na_visita": True}],
    ],
)
def test_ingestao_rejeita_payload_invalido(cliente, db_session, payload):
    """Tipo invalido ou payload fora do schema responde 422 e nao grava nada."""
    resposta = _enviar(cliente, payload)

    assert resposta.status_code == 422
    assert resposta.json() == {"detail": "Evento invalido."}
    assert not _eventos(db_session)


def test_ingestao_rejeita_json_malformado(cliente, db_session):
    """Corpo que nao e JSON responde 422 sem ecoar o conteudo."""
    resposta = cliente.post(
        "/analytics/eventos",
        content=b"tipo=visita_site",
        headers={**CABECALHOS_SITE, "Content-Type": "application/json"},
    )

    assert resposta.status_code == 422
    assert "visita_site" not in resposta.text
    assert not _eventos(db_session)


def test_ingestao_rejeita_payload_grande(cliente, db_session):
    """Corpo acima do limite responde 413 e nao grava nada."""
    payload = {
        "tipo": "visita_site",
        "primeiro_na_visita": True,
        "utm_campaign": "x" * (ingestao.TAMANHO_MAXIMO_PAYLOAD_BYTES + 1),
    }

    resposta = _enviar(cliente, payload)

    assert resposta.status_code == 413
    assert not _eventos(db_session)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("utm_source", "x" * 101),
        ("utm_medium", "<script>"),
        ("utm_campaign", "-comeca-com-hifen"),
        ("referrer_host", "https://www.google.com/search?q=email@exemplo.com"),
        ("referrer_host", "a" * 256),
        ("referrer_host", "dominio com espaco.com"),
    ],
)
def test_ingestao_descarta_campo_malformado_sem_rejeitar(
    cliente, db_session, caplog, campo, valor
):
    """UTM longa ou malformada e referrer que nao e dominio viram None e o evento e gravado."""
    with caplog.at_level(logging.WARNING, logger="src.analytics.ingestao"):
        resposta = _enviar(
            cliente,
            {"tipo": "visita_site", "primeiro_na_visita": True, campo: valor},
        )

    assert resposta.status_code == 204
    [evento] = _eventos(db_session)
    assert getattr(evento, campo) is None
    assert evento.canal == CanalAquisicao.direto
    assert f"campo_descartado campo={campo}" in caplog.text
    assert valor not in caplog.text


def test_ingestao_aceita_utm_no_limite(cliente, db_session):
    """UTM com exatamente 100 caracteres e mantida."""
    valor = "a" * 100

    _enviar(cliente, {"tipo": "visita_site", "primeiro_na_visita": True, "utm_campaign": valor})

    [evento] = _eventos(db_session)
    assert evento.utm_campaign == valor


@pytest.mark.parametrize("campo", ["unidade_id", "produto_id"])
@pytest.mark.parametrize("valor", [999999, 0, -1])
def test_ingestao_ignora_ids_inexistentes(cliente, db_session, campo, valor):
    """unidade_id e produto_id inexistentes viram None sem rejeitar o evento."""
    resposta = _enviar(
        cliente,
        {"tipo": "selecao_unidade", "primeiro_na_visita": True, campo: valor},
    )

    assert resposta.status_code == 204
    [evento] = _eventos(db_session)
    assert getattr(evento, campo) is None


def test_ingestao_grava_horario_truncado(cliente, db_session):
    """ocorrido_em e definido pelo servidor, em UTC e sem minutos ou segundos."""
    antes = ingestao.horario_truncado_utc()
    _enviar(
        cliente,
        {
            "tipo": "visita_site",
            "primeiro_na_visita": True,
            "ocorrido_em": "2020-01-01T10:37:00",
        },
    )
    depois = ingestao.horario_truncado_utc()

    [evento] = _eventos(db_session)
    assert evento.ocorrido_em.minute == 0
    assert evento.ocorrido_em.second == 0
    assert evento.ocorrido_em.microsecond == 0
    assert antes <= evento.ocorrido_em <= depois


def test_horario_truncado_converte_para_utc():
    """23:59 em Brasilia vira 02:00 UTC do dia seguinte, sem fuso."""
    brasilia = repository.FUSO_SAO_PAULO
    momento = datetime(2026, 10, 25, 23, 59, 59, tzinfo=brasilia)

    assert ingestao.horario_truncado_utc(momento) == datetime(2026, 10, 26, 2, 0)


def test_ingestao_ignora_token_e_nao_grava_dados_de_autenticacao(cliente, db_session):
    """A ingestao funciona sem autenticacao e ignora um token enviado."""
    app.dependency_overrides.pop(get_current_user, None)

    resposta = _enviar(
        cliente,
        {"tipo": "clique_pedir", "primeiro_na_visita": True},
        {**CABECALHOS_SITE, "Authorization": "Bearer token-invalido"},
    )

    assert resposta.status_code == 204
    [evento] = _eventos(db_session)
    colunas = set(EventoAnalytics.__table__.columns.keys())
    assert colunas == {
        "id",
        "tipo",
        "primeiro_na_visita",
        "unidade_id",
        "produto_id",
        "canal",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "referrer_host",
        "ocorrido_em",
        "versao_coleta",
    }
    assert evento.tipo == TipoEventoAnalytics.clique_pedir


# ------------------------------------------------------- filtro de trafego


@pytest.mark.parametrize(
    "cabecalhos",
    [
        {"User-Agent": USER_AGENT_NAVEGADOR},
        {"Origin": "https://outro-site.test", "User-Agent": USER_AGENT_NAVEGADOR},
        {"Origin": "http://site.paraiba.test", "User-Agent": USER_AGENT_NAVEGADOR},
        {"Origin": "null", "User-Agent": USER_AGENT_NAVEGADOR},
    ],
)
def test_filtro_descarta_origem_invalida(cliente, db_session, cabecalhos):
    """Requisicao sem Origin do site responde 204 e nao grava nada."""
    resposta = _enviar(cliente, {"tipo": "visita_site", "primeiro_na_visita": True}, cabecalhos)

    assert resposta.status_code == 204
    assert not _eventos(db_session)


@pytest.mark.parametrize(
    "user_agent",
    [
        "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
        "Mozilla/5.0 (compatible; bingbot/2.0)",
        "Mozilla/5.0 (X11; Linux x86_64) HeadlessChrome/130.0 Safari/537.36",
        "facebookexternalhit/1.1",
        "Baiduspider",
        "curl/8.4.0",
        "python-requests/2.31.0",
        "",
    ],
)
def test_filtro_descarta_robo(cliente, db_session, user_agent):
    """User-Agent de robo conhecido ou vazio responde 204 e nao grava nada."""
    resposta = _enviar(
        cliente,
        {"tipo": "visita_site", "primeiro_na_visita": True},
        {"Origin": ORIGEM_SITE, "User-Agent": user_agent},
    )

    assert resposta.status_code == 204
    assert not _eventos(db_session)


def test_filtro_descarta_antes_de_validar_payload(cliente, db_session):
    """Lixo de fora do site recebe 204, sem revelar que o payload e invalido."""
    resposta = _enviar(cliente, {"tipo": "invalido"}, {"User-Agent": "curl/8.4.0"})

    assert resposta.status_code == 204
    assert not _eventos(db_session)


def test_filtro_aceita_origem_com_barra_no_env(cliente, db_session, monkeypatch):
    """FRONTEND_BASE_URL com barra final ou caminho continua aceitando a origem."""
    monkeypatch.setattr(ingestao.settings, "frontend_base_url", f"{ORIGEM_SITE}/app/")

    resposta = _enviar(cliente, {"tipo": "visita_site", "primeiro_na_visita": True})

    assert resposta.status_code == 204
    assert len(_eventos(db_session)) == 1


# -------------------------------------------------------------------- canal


@pytest.mark.parametrize(
    ("origem", "canal_esperado"),
    [
        ({"utm_source": "instagram"}, CanalAquisicao.instagram),
        ({"utm_source": "qrcode"}, CanalAquisicao.qrcode),
        ({"utm_source": "newsletter"}, CanalAquisicao.campanha_outros),
        (
            {"utm_source": "newsletter", "referrer_host": "l.instagram.com"},
            CanalAquisicao.campanha_outros,
        ),
        ({"referrer_host": "instagram.com"}, CanalAquisicao.instagram),
        ({"referrer_host": "l.instagram.com"}, CanalAquisicao.instagram),
        ({"referrer_host": "www.google.com"}, CanalAquisicao.busca),
        ({"referrer_host": "www.google.com.br"}, CanalAquisicao.busca),
        ({"referrer_host": "www.bing.com"}, CanalAquisicao.busca),
        ({"referrer_host": "duckduckgo.com"}, CanalAquisicao.busca),
        ({"referrer_host": "br.search.yahoo.com"}, CanalAquisicao.busca),
        ({"referrer_host": "www.facebook.com"}, CanalAquisicao.outros_sites),
        ({"referrer_host": "fakeinstagram.com"}, CanalAquisicao.outros_sites),
        ({"referrer_host": "docs.google.com"}, CanalAquisicao.outros_sites),
        ({}, CanalAquisicao.direto),
        ({"utm_source": "   ", "referrer_host": ""}, CanalAquisicao.direto),
    ],
)
def test_canal_segue_tabela_de_mapeamento(cliente, db_session, origem, canal_esperado):
    """Cada linha da tabela de canal, aplicada em ordem na ingestao."""
    _enviar(cliente, {"tipo": "visita_site", "primeiro_na_visita": True, **origem})

    [evento] = _eventos(db_session)
    assert evento.canal == canal_esperado


# ------------------------------------------------------------------ periodo


def test_periodo_inclui_dia_atual_em_horario_de_brasilia():
    """Ultimos 7 dias vao da meia-noite de 6 dias atras ate a meia-noite de amanha, em Brasilia."""
    inicio, fim = repository.intervalo_periodo(PeriodoAquisicao.ultimos_7_dias, AGORA)

    assert inicio == datetime(2026, 10, 20, 3, 0)
    assert fim == datetime(2026, 10, 27, 3, 0)


def test_periodo_usa_o_dia_de_brasilia_quando_utc_ja_virou():
    """As 01h UTC ainda e o dia anterior em Brasilia."""
    madrugada_utc = datetime(2026, 10, 27, 1, 0, tzinfo=UTC)

    inicio, fim = repository.intervalo_periodo(PeriodoAquisicao.ultimos_7_dias, madrugada_utc)

    assert inicio == datetime(2026, 10, 20, 3, 0)
    assert fim == datetime(2026, 10, 27, 3, 0)


def test_evento_as_23h30_de_brasilia_entra_no_dia_certo(db_session):
    """23h30 do dia anterior ao periodo fica fora; 00h30 do primeiro dia entra."""
    vespera_23h30 = ingestao.horario_truncado_utc(
        datetime(2026, 10, 19, 23, 30, tzinfo=repository.FUSO_SAO_PAULO)
    )
    primeiro_dia_00h30 = ingestao.horario_truncado_utc(
        datetime(2026, 10, 20, 0, 30, tzinfo=repository.FUSO_SAO_PAULO)
    )
    hoje_23h30 = ingestao.horario_truncado_utc(
        datetime(2026, 10, 26, 23, 30, tzinfo=repository.FUSO_SAO_PAULO)
    )
    _criar_eventos(db_session, TipoEventoAnalytics.visita_site, ocorrido_em=vespera_23h30)
    _criar_eventos(db_session, TipoEventoAnalytics.visita_site, ocorrido_em=primeiro_dia_00h30)
    _criar_eventos(db_session, TipoEventoAnalytics.visita_site, ocorrido_em=hoje_23h30)

    resultado = repository.obter_aquisicao(
        db_session, periodo=PeriodoAquisicao.ultimos_7_dias, agora=AGORA
    )

    assert resultado.indicadores.visitantes == 2


@pytest.mark.parametrize(
    ("periodo", "visitantes"),
    [
        (PeriodoAquisicao.ultimos_7_dias, 1),
        (PeriodoAquisicao.ultimos_30_dias, 2),
        (PeriodoAquisicao.ultimos_90_dias, 3),
    ],
)
def test_filtro_de_periodo(db_session, periodo, visitantes):
    """Cada periodo conta apenas os eventos dentro dos seus limites."""
    _criar_eventos(db_session, TipoEventoAnalytics.visita_site, ocorrido_em=datetime(2026, 10, 25, 12))
    _criar_eventos(db_session, TipoEventoAnalytics.visita_site, ocorrido_em=datetime(2026, 10, 1, 12))
    _criar_eventos(db_session, TipoEventoAnalytics.visita_site, ocorrido_em=datetime(2026, 8, 1, 12))
    _criar_eventos(db_session, TipoEventoAnalytics.visita_site, ocorrido_em=datetime(2026, 7, 1, 12))

    resultado = repository.obter_aquisicao(db_session, periodo=periodo, agora=AGORA)

    assert resultado.indicadores.visitantes == visitantes


# -------------------------------------------------------------------- funil


def test_funil_conta_so_primeiro_na_visita_e_indicadores_contam_total(db_session):
    """Funil e visitantes usam primeiro_na_visita; os cards usam o total de eventos."""
    tipos = TipoEventoAnalytics
    _criar_eventos(db_session, tipos.visita_site, 10)
    _criar_eventos(db_session, tipos.visita_site, 3, primeiro=False)
    _criar_eventos(db_session, tipos.abertura_cardapio, 8)
    _criar_eventos(db_session, tipos.abertura_cardapio, 2, primeiro=False)
    _criar_eventos(db_session, tipos.selecao_unidade, 6)
    _criar_eventos(db_session, tipos.visualizacao_produto, 5)
    _criar_eventos(db_session, tipos.visualizacao_produto, 7, primeiro=False)
    _criar_eventos(db_session, tipos.clique_pedir, 2)
    _criar_eventos(db_session, tipos.clique_pedir, 1, primeiro=False)

    resultado = repository.obter_aquisicao(db_session, agora=AGORA)

    assert [etapa.etapa for etapa in resultado.funil] == list(repository.ETAPAS_FUNIL)
    assert [etapa.volume for etapa in resultado.funil] == [10, 8, 6, 5, 2]
    assert resultado.indicadores.model_dump() == {
        "visitantes": 10,
        "visualizacoes_cardapio": 10,
        "produtos_visualizados": 12,
        "cliques_pedir": 3,
        "taxa_visita_clique": pytest.approx(20),
    }
    assert str(resultado.indicadores.taxa_visita_clique) == "20.00"


def test_funil_calcula_conversao_perda_e_maior_abandono(db_session):
    """Conversao e perda por etapa; maior abandono e a maior perda relativa."""
    tipos = TipoEventoAnalytics
    _criar_eventos(db_session, tipos.visita_site, 10)
    _criar_eventos(db_session, tipos.abertura_cardapio, 8)
    _criar_eventos(db_session, tipos.selecao_unidade, 6)
    _criar_eventos(db_session, tipos.visualizacao_produto, 3)
    _criar_eventos(db_session, tipos.clique_pedir, 2)

    etapas = _etapas(repository.obter_aquisicao(db_session, agora=AGORA))

    assert etapas[tipos.visita_site].conversao_etapa_anterior is None
    assert etapas[tipos.visita_site].perda == 0
    assert str(etapas[tipos.abertura_cardapio].conversao_etapa_anterior) == "80.00"
    assert etapas[tipos.abertura_cardapio].perda == 2
    assert str(etapas[tipos.selecao_unidade].conversao_etapa_anterior) == "75.00"
    assert str(etapas[tipos.visualizacao_produto].conversao_etapa_anterior) == "50.00"
    assert etapas[tipos.visualizacao_produto].perda == 3
    assert str(etapas[tipos.clique_pedir].conversao_etapa_anterior) == "66.67"
    assert [etapa for etapa, dados in etapas.items() if dados.maior_abandono] == [
        tipos.visualizacao_produto
    ]


def test_funil_etapa_maior_que_anterior(db_session):
    """Etapa maior que a anterior tem conversao acima de 100% e perda negativa, sem ser abandono."""
    tipos = TipoEventoAnalytics
    _criar_eventos(db_session, tipos.visita_site, 10)
    _criar_eventos(db_session, tipos.abertura_cardapio, 4)
    _criar_eventos(db_session, tipos.selecao_unidade, 6)
    _criar_eventos(db_session, tipos.visualizacao_produto, 6)
    _criar_eventos(db_session, tipos.clique_pedir, 9)

    etapas = _etapas(repository.obter_aquisicao(db_session, agora=AGORA))

    assert str(etapas[tipos.selecao_unidade].conversao_etapa_anterior) == "150.00"
    assert etapas[tipos.selecao_unidade].perda == -2
    assert str(etapas[tipos.clique_pedir].conversao_etapa_anterior) == "150.00"
    assert etapas[tipos.clique_pedir].perda == -3
    assert etapas[tipos.visualizacao_produto].perda == 0
    assert [etapa for etapa, dados in etapas.items() if dados.maior_abandono] == [
        tipos.abertura_cardapio
    ]


def test_funil_sem_perda_positiva_nao_marca_abandono(db_session):
    """Se nenhuma etapa perde visitas, nenhuma e marcada como maior abandono."""
    for tipo in repository.ETAPAS_FUNIL:
        _criar_eventos(db_session, tipo, 5)

    resultado = repository.obter_aquisicao(db_session, agora=AGORA)

    assert not any(etapa.maior_abandono for etapa in resultado.funil)
    assert str(resultado.indicadores.taxa_visita_clique) == "100.00"


def test_funil_etapa_anterior_zerada_nao_divide_por_zero(db_session):
    """Conversao fica None quando a etapa anterior e zero."""
    _criar_eventos(db_session, TipoEventoAnalytics.clique_pedir, 3)

    etapas = _etapas(repository.obter_aquisicao(db_session, agora=AGORA))

    assert etapas[TipoEventoAnalytics.clique_pedir].conversao_etapa_anterior is None
    assert etapas[TipoEventoAnalytics.clique_pedir].perda == -3
    assert not any(etapa.maior_abandono for etapa in etapas.values())


def test_aquisicao_sem_resultados(cliente):
    """Sem eventos: volumes zero, taxas None e nenhum maior abandono."""
    resposta = cliente.get("/analytics/aquisicao")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert [etapa["etapa"] for etapa in corpo["funil"]] == [
        "visita_site",
        "abertura_cardapio",
        "selecao_unidade",
        "visualizacao_produto",
        "clique_pedir",
    ]
    for etapa in corpo["funil"]:
        assert etapa["volume"] == 0
        assert etapa["conversao_etapa_anterior"] is None
        assert etapa["perda"] == 0
        assert etapa["maior_abandono"] is False
    assert corpo["indicadores"] == {
        "visitantes": 0,
        "visualizacoes_cardapio": 0,
        "produtos_visualizados": 0,
        "cliques_pedir": 0,
        "taxa_visita_clique": None,
    }


# ------------------------------------------------------------------ filtros


def test_filtros_de_unidade_e_canal(cliente, db_session, unidade):
    """Unidade e canal restringem os eventos contados, isolados e combinados."""
    agora = ingestao.horario_truncado_utc()
    tipos = TipoEventoAnalytics
    _criar_eventos(
        db_session, tipos.clique_pedir, 2,
        ocorrido_em=agora, canal=CanalAquisicao.instagram, unidade_id=unidade.id,
    )
    _criar_eventos(
        db_session, tipos.clique_pedir, 3,
        ocorrido_em=agora, canal=CanalAquisicao.qrcode, unidade_id=unidade.id,
    )
    _criar_eventos(
        db_session, tipos.clique_pedir, 4,
        ocorrido_em=agora, canal=CanalAquisicao.instagram,
    )

    def cliques(**params) -> int:
        resposta = cliente.get("/analytics/aquisicao", params=params)
        assert resposta.status_code == 200
        return resposta.json()["indicadores"]["cliques_pedir"]

    assert cliques() == 9
    assert cliques(unidade_id=unidade.id) == 5
    assert cliques(canal="instagram") == 6
    assert cliques(unidade_id=unidade.id, canal="instagram") == 2
    assert cliques(periodo="ultimos_7_dias", canal="direto") == 0


@pytest.mark.parametrize(
    "params",
    [
        {"periodo": "ontem"},
        {"canal": "tiktok"},
        {"unidade_id": 0},
        {"unidade_id": "abc"},
    ],
)
def test_aquisicao_rejeita_filtro_invalido(cliente, params):
    """Valores fora dos enums ou ids invalidos respondem 422."""
    assert cliente.get("/analytics/aquisicao", params=params).status_code == 422


def test_aquisicao_exige_autenticacao(cliente):
    """A leitura do painel nao e publica."""
    app.dependency_overrides.pop(get_current_user, None)

    resposta = cliente.get("/analytics/aquisicao")

    assert resposta.status_code == 401
