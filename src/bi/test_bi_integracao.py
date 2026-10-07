from datetime import date, datetime, time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.bi import repository
from src.clientes.model import Cliente
from src.main import app
from src.pedidos.model import ItemPedido, Pedido, StatusItemPedido, StatusPedido
from src.produtos.model import Categoria, Produto, ProdutoVariacao, Subcategoria, TipoVariacao
from src.unidades.model import Endereco, Unidade

TEST_DATABASE_URL = "sqlite+pysqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def _mes_anterior(momento: datetime) -> datetime:
    if momento.month == 1:
        return momento.replace(year=momento.year - 1, month=12)
    return momento.replace(month=momento.month - 1)


@pytest.fixture(name="db_session", scope="function")
def fixture_db_session():
    """Cria uma sessao SQLite isolada para os testes de BI."""
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


@pytest.fixture(name="cliente")
def fixture_cliente():
    """Cria o TestClient usado nos cenarios de BI."""
    return TestClient(app)


@pytest.fixture(name="pedido_pago")
def fixture_pedido_pago(db_session):
    """Cria um pedido pago com item vendido para alimentar o dashboard."""
    endereco = Endereco(
        cep="71900000",
        logradouro="Aguas Claras",
        numero="1",
        bairro="Aguas Claras",
        cidade="Brasilia",
        estado="DF",
    )
    unidade = Unidade(
        nome="Unidade BI",
        abertura=time(16, 30),
        fechamento=time(23, 59),
        descricao="Unidade teste",
        endereco=endereco,
    )
    categoria = Categoria(nome="Hot-Dog")
    subcategoria = Subcategoria(nome="Lanches", categoria=categoria)
    produto = Produto(
        nome="Paraiba Monster XL",
        descricao="Produto destaque",
        ativo=True,
        pontos_fidelidade_por_unidade=1,
        disponivel_todas_unidades=True,
        subcategoria=subcategoria,
    )
    variacao = ProdutoVariacao(
        produto=produto,
        nome="Normal",
        tipo=TipoVariacao.normal,
        preco=Decimal("30.00"),
        ativo=True,
    )
    pedido = Pedido(
        unidade=unidade,
        nome_comanda="Mesa 1",
        status=StatusPedido.pago,
        subtotal=Decimal("60.00"),
        desconto_fidelidade=Decimal("0.00"),
        total=Decimal("60.00"),
        created_at=datetime.now().replace(hour=13, minute=0, second=0, microsecond=0),
        fechado_em=datetime.now(),
    )
    pedido.itens = [
        ItemPedido(
            produto_variacao=variacao,
            produto_id=1,
            produto_nome="Paraiba Monster XL",
            produto_variacao_nome="Normal",
            quantidade=2,
            preco_unitario=Decimal("30.00"),
            status=StatusItemPedido.entregue,
            lote=1,
            created_at=pedido.created_at,
        )
    ]
    db_session.add(pedido)
    db_session.commit()
    return pedido


def _base_bi(db_session):
    endereco = Endereco(
        cep="71900000",
        logradouro="Aguas Claras",
        numero="1",
        bairro="Aguas Claras",
        cidade="Brasilia",
        estado="DF",
    )
    unidade = Unidade(
        nome="Unidade BI",
        abertura=time(16, 30),
        fechamento=time(23, 59),
        descricao="Unidade teste",
        endereco=endereco,
    )
    categoria = Categoria(nome="Hot-Dog")
    subcategoria = Subcategoria(nome="Lanches", categoria=categoria)
    produto_a = Produto(
        nome="Paraiba Monster XL",
        ativo=True,
        pontos_fidelidade_por_unidade=1,
        disponivel_todas_unidades=True,
        subcategoria=subcategoria,
    )
    produto_b = Produto(
        nome="Paraiba Classico",
        ativo=True,
        pontos_fidelidade_por_unidade=1,
        disponivel_todas_unidades=True,
        subcategoria=subcategoria,
    )
    variacao_a = ProdutoVariacao(
        produto=produto_a,
        nome="Normal",
        tipo=TipoVariacao.normal,
        preco=Decimal("100.00"),
        ativo=True,
    )
    variacao_b = ProdutoVariacao(
        produto=produto_b,
        nome="Normal",
        tipo=TipoVariacao.normal,
        preco=Decimal("100.00"),
        ativo=True,
    )
    db_session.add_all([unidade, variacao_a, variacao_b])
    db_session.flush()
    return unidade, produto_a, produto_b, variacao_a, variacao_b


def _pedido_com_itens(unidade, created_at, subtotal, total, itens):
    pedido = Pedido(
        unidade=unidade,
        nome_comanda="Mesa BI",
        status=StatusPedido.pago,
        subtotal=Decimal(subtotal),
        desconto_fidelidade=Decimal(subtotal) - Decimal(total),
        total=Decimal(total),
        created_at=created_at,
        fechado_em=created_at,
    )
    pedido.itens = [
        ItemPedido(
            produto_variacao=variacao,
            produto_id=produto.id,
            produto_nome=produto.nome,
            produto_variacao_nome=variacao.nome,
            quantidade=quantidade,
            preco_unitario=Decimal(preco),
            status=StatusItemPedido.entregue,
            lote=1,
            created_at=created_at,
        )
        for produto, variacao, quantidade, preco in itens
    ]
    return pedido


@pytest.mark.integration
@pytest.mark.usefixtures("pedido_pago")
def test_dashboard_retorna_indicadores_agregados(cliente):
    """Garante que o BI consolida pedidos e itens vendidos."""
    resposta = cliente.get("/bi/dashboard")

    assert resposta.status_code == 200
    body = resposta.json()
    assert body["kpis"]["receita_bruta"] == "60.00"
    assert body["kpis"]["lucro_liquido"] == "60.00"
    assert body["kpis"]["ticket_medio"] == "60.00"
    assert body["kpis"]["total_pedidos"] == 1
    assert body["top_produtos"][0]["nome"] == "Paraiba Monster XL"
    assert body["top_produtos"][0]["quantidade"] == 2
    assert body["mix_produtos"][0]["percentual"] == "100.00"
    assert body["destaque"]["nome"] == "Paraiba Monster XL"


@pytest.mark.integration
def test_dashboard_usa_receita_bruta_e_rateia_liquido(db_session):
    """Garante que vendas totais usam bruto e destaque separa bruto/liquido."""
    unidade, produto_a, produto_b, variacao_a, variacao_b = _base_bi(db_session)
    agora = datetime.now().replace(day=14, hour=13, minute=0, second=0, microsecond=0)
    anterior = _mes_anterior(agora)
    pedidos = [
        _pedido_com_itens(
            unidade,
            anterior,
            "100.00",
            "100.00",
            [(produto_a, variacao_a, 1, "100.00")],
        ),
        _pedido_com_itens(
            unidade,
            agora,
            "200.00",
            "100.00",
            [(produto_a, variacao_a, 2, "100.00")],
        ),
        _pedido_com_itens(
            unidade,
            agora,
            "100.00",
            "100.00",
            [(produto_b, variacao_b, 1, "100.00")],
        ),
    ]
    db_session.add_all(pedidos)
    db_session.commit()

    dashboard = repository.obter_dashboard(db_session)

    assert dashboard.kpis.receita_bruta == Decimal("400.00")
    assert dashboard.kpis.lucro_liquido == Decimal("300.00")
    assert dashboard.kpis.ticket_medio == Decimal("133.33")
    assert dashboard.vendas_totais == Decimal("400.00")
    assert dashboard.top_produtos[0].nome == "Paraiba Monster XL"
    assert dashboard.top_produtos[0].variacao == Decimal("100.00")
    assert dashboard.destaque.margem_ganho == Decimal("75.00")
    assert dashboard.destaque.margem_liquida == Decimal("66.67")


@pytest.mark.integration
def test_dashboard_variacao_de_zero_para_venda_retorna_100(db_session):
    """Garante que crescimento sem base anterior nao fica mascarado como 0%."""
    unidade, produto_a, _produto_b, variacao_a, _variacao_b = _base_bi(db_session)
    agora = datetime.now().replace(day=14, hour=13, minute=0, second=0, microsecond=0)
    pedido = _pedido_com_itens(
        unidade,
        agora,
        "100.00",
        "100.00",
        [(produto_a, variacao_a, 1, "100.00")],
    )
    db_session.add(pedido)
    db_session.commit()

    dashboard = repository.obter_dashboard(db_session)

    assert dashboard.kpis.variacao_receita_bruta == Decimal("100.00")
    assert dashboard.top_produtos[0].variacao == Decimal("100.00")


def _segunda_unidade(db_session):
    unidade = Unidade(
        nome="Unidade Norte",
        abertura=time(16, 30),
        fechamento=time(23, 59),
        descricao="Segunda unidade",
        endereco=Endereco(
            cep="70000000",
            logradouro="Asa Norte",
            numero="2",
            bairro="Asa Norte",
            cidade="Brasilia",
            estado="DF",
        ),
    )
    db_session.add(unidade)
    db_session.flush()
    return unidade


@pytest.mark.integration
def test_dashboard_intervalo_compara_com_periodo_anterior(db_session):
    """Garante que o intervalo de datas filtra e compara com o periodo anterior de mesmo tamanho."""
    unidade, produto_a, _produto_b, variacao_a, _variacao_b = _base_bi(db_session)

    def pedido(created_at, valor, quantidade=1):
        preco = str(Decimal(valor) / quantidade)
        return _pedido_com_itens(unidade, created_at, valor, valor, [(produto_a, variacao_a, quantidade, preco)])

    db_session.add_all(
        [
            # Periodo anterior (01/03 a 10/03): 1 pedido de 100.
            pedido(datetime(2026, 3, 5, 13), "100.00"),
            # Periodo filtrado (11/03 a 20/03): 2 pedidos somando 300.
            pedido(datetime(2026, 3, 11, 12), "100.00"),
            pedido(datetime(2026, 3, 20, 23), "200.00", quantidade=2),
            # Fora de qualquer um dos periodos.
            pedido(datetime(2026, 3, 21, 13), "999.00"),
        ]
    )
    db_session.commit()

    dashboard = repository.obter_dashboard(db_session, data_inicio=date(2026, 3, 11), data_fim=date(2026, 3, 20))

    assert dashboard.kpis.receita_bruta == Decimal("300.00")
    assert dashboard.kpis.total_pedidos == 2
    assert dashboard.kpis.variacao_receita_bruta == Decimal("200.00")
    assert dashboard.kpis.variacao_total_pedidos == Decimal("100.00")
    assert dashboard.top_produtos[0].variacao == Decimal("200.00")
    assert dashboard.vendas_por_hora[-1].hora == "23h"
    assert dashboard.agrupamento_periodo == "dia"
    assert len(dashboard.vendas_por_periodo) == 10
    assert dashboard.vendas_por_periodo[0].periodo == "2026-03-11"
    assert dashboard.vendas_por_periodo[0].receita_bruta == Decimal("100.00")
    assert dashboard.vendas_por_periodo[1].total_pedidos == 0


@pytest.mark.integration
def test_dashboard_intervalo_longo_agrupa_por_mes(db_session):
    """Garante que intervalos longos agrupam a serie de vendas por mes."""
    unidade, produto_a, _produto_b, variacao_a, _variacao_b = _base_bi(db_session)
    db_session.add(
        _pedido_com_itens(unidade, datetime(2026, 2, 10, 13), "50.00", "50.00", [(produto_a, variacao_a, 1, "50.00")])
    )
    db_session.commit()

    dashboard = repository.obter_dashboard(db_session, data_inicio=date(2026, 1, 1), data_fim=date(2026, 6, 30))

    assert dashboard.agrupamento_periodo == "mes"
    assert [venda.periodo for venda in dashboard.vendas_por_periodo] == [
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
    ]
    assert dashboard.vendas_por_periodo[1].receita_bruta == Decimal("50.00")


@pytest.mark.integration
def test_dashboard_desempenho_por_unidade(db_session):
    """Garante o ranking de unidades com participacao na receita."""
    unidade, produto_a, _produto_b, variacao_a, _variacao_b = _base_bi(db_session)
    unidade_norte = _segunda_unidade(db_session)
    momento = datetime(2026, 4, 10, 13)
    db_session.add_all(
        [
            _pedido_com_itens(unidade, momento, "100.00", "100.00", [(produto_a, variacao_a, 1, "100.00")]),
            _pedido_com_itens(unidade_norte, momento, "200.00", "200.00", [(produto_a, variacao_a, 2, "100.00")]),
            _pedido_com_itens(unidade_norte, momento, "100.00", "100.00", [(produto_a, variacao_a, 1, "100.00")]),
        ]
    )
    db_session.commit()

    dashboard = repository.obter_dashboard(db_session, data_inicio=date(2026, 4, 1), data_fim=date(2026, 4, 30))

    assert [unidade.nome for unidade in dashboard.desempenho_unidades] == ["Unidade Norte", "Unidade BI"]
    assert dashboard.desempenho_unidades[0].total_pedidos == 2
    assert dashboard.desempenho_unidades[0].receita_bruta == Decimal("300.00")
    assert dashboard.desempenho_unidades[0].ticket_medio == Decimal("150.00")
    assert dashboard.desempenho_unidades[0].participacao == Decimal("75.00")

    filtrado = repository.obter_dashboard(
        db_session,
        unidade_id=unidade.id,
        data_inicio=date(2026, 4, 1),
        data_fim=date(2026, 4, 30),
    )
    assert [unidade.nome for unidade in filtrado.desempenho_unidades] == ["Unidade BI"]
    assert filtrado.desempenho_unidades[0].participacao == Decimal("100.00")


@pytest.mark.integration
def test_dashboard_metricas_de_fidelidade(db_session):
    """Garante as metricas de fidelidade a partir dos pedidos com cliente."""
    unidade, produto_a, _produto_b, variacao_a, _variacao_b = _base_bi(db_session)
    maria = Cliente(nome="Maria", telefone="61999990001", pontos_fidelidade=7)
    joao = Cliente(nome="Joao", telefone="61999990002", pontos_fidelidade=2)
    db_session.add_all([maria, joao])
    db_session.flush()
    momento = datetime(2026, 5, 10, 19)
    pedidos = [
        _pedido_com_itens(unidade, momento, "100.00", "90.00", [(produto_a, variacao_a, 1, "100.00")]),
        _pedido_com_itens(unidade, momento, "100.00", "100.00", [(produto_a, variacao_a, 1, "100.00")]),
        _pedido_com_itens(unidade, momento, "50.00", "50.00", [(produto_a, variacao_a, 1, "50.00")]),
        _pedido_com_itens(unidade, momento, "30.00", "30.00", [(produto_a, variacao_a, 1, "30.00")]),
    ]
    pedidos[0].cliente = maria
    pedidos[0].pontos_fidelidade_utilizados = 10
    pedidos[1].cliente = maria
    pedidos[2].cliente = joao
    db_session.add_all(pedidos)
    db_session.commit()

    fidelidade = repository.obter_dashboard(
        db_session,
        data_inicio=date(2026, 5, 1),
        data_fim=date(2026, 5, 31),
    ).fidelidade

    assert fidelidade.pedidos_com_cliente == 3
    assert fidelidade.percentual_pedidos_com_cliente == Decimal("75.00")
    assert fidelidade.clientes_unicos == 2
    assert fidelidade.pontos_resgatados == 10
    assert fidelidade.descontos_concedidos == Decimal("10.00")
    assert fidelidade.ticket_medio_com_cliente == Decimal("83.33")
    assert fidelidade.ticket_medio_sem_cliente == Decimal("30.00")
    assert [cliente.nome for cliente in fidelidade.top_clientes] == ["Maria", "Joao"]
    assert fidelidade.top_clientes[0].total_pedidos == 2
    assert fidelidade.top_clientes[0].receita_bruta == Decimal("200.00")
    assert fidelidade.top_clientes[0].pontos_atuais == 7


@pytest.mark.integration
@pytest.mark.parametrize(
    "params",
    [
        {"data_inicio": "2026-05-01"},
        {"data_fim": "2026-05-01"},
        {"data_inicio": "2026-05-10", "data_fim": "2026-05-01"},
    ],
)
def test_dashboard_rejeita_intervalo_invalido(cliente, params):
    """Garante que o intervalo precisa das duas datas em ordem."""
    resposta = cliente.get("/bi/dashboard", params=params)

    assert resposta.status_code == 422


@pytest.mark.integration
@pytest.mark.usefixtures("pedido_pago")
def test_dashboard_aceita_intervalo_pela_api(cliente):
    """Garante que a rota repassa o intervalo de datas e devolve os blocos novos."""
    hoje = date.today().isoformat()

    resposta = cliente.get("/bi/dashboard", params={"data_inicio": hoje, "data_fim": hoje})

    assert resposta.status_code == 200
    body = resposta.json()
    assert body["kpis"]["receita_bruta"] == "60.00"
    assert body["vendas_por_periodo"] == [{"periodo": hoje, "receita_bruta": "60.00", "total_pedidos": 1}]
    assert body["desempenho_unidades"][0]["nome"] == "Unidade BI"
    assert body["fidelidade"]["pedidos_com_cliente"] == 0
