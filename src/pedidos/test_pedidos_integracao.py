from datetime import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# pylint: disable=redefined-outer-name

from src.clientes.model import Cliente
from src.database import Base, get_db
from src.main import app
from src.produtos.model import (
    Categoria,
    Produto,
    ProdutoAdicional,
    ProdutoVariacao,
    Subcategoria,
    TipoVariacao,
)
from src.unidades.model import Endereco, Unidade


TEST_DATABASE_URL = "sqlite+pysqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """Cria uma sessao SQLite isolada para cada teste de pedidos."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def override_get_db(db_session):
    """Substitui a dependencia get_db pela sessao de teste."""
    def _get_db():
        """Fornece a sessao fake para o FastAPI durante o teste."""
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(name="cliente")
def fixture_cliente():
    """Cria o TestClient usado nos cenarios de pedidos."""
    return TestClient(app)


@pytest.fixture
def cardapio_base(db_session):
    """Cria unidade, produto, variacao, adicionais e cliente base."""
    endereco = Endereco(
        cep="71900000",
        logradouro="Aguas Claras",
        numero="1",
        bairro="Aguas Claras",
        cidade="Brasilia",
        estado="DF",
    )
    db_session.add(endereco)
    db_session.flush()

    unidade = Unidade(
        nome="Paraiba Hot Dog Sul Aguas Claras",
        abertura=time(16, 30),
        fechamento=time(23, 59),
        descricao="Unidade teste",
        endereco_id=endereco.id,
    )
    categoria = Categoria(nome="Hot-Dog")
    db_session.add_all([unidade, categoria])
    db_session.flush()

    subcategoria = Subcategoria(nome="Molho", categoria_id=categoria.id)
    db_session.add(subcategoria)
    db_session.flush()

    produto = Produto(
        nome="Tradicional",
        descricao="Pao, salsicha, queijo, molho, milho e batata palha.",
        ativo=True,
        pontos_fidelidade_por_unidade=1,
        disponivel_todas_unidades=True,
        subcategoria_id=subcategoria.id,
    )
    db_session.add(produto)
    db_session.flush()

    variacao = ProdutoVariacao(
        produto_id=produto.id,
        nome="Tradicional",
        tipo=TipoVariacao.normal,
        preco=Decimal("19.90"),
        ativo=True,
    )
    adicional_ervas = ProdutoAdicional(
        produto_id=produto.id,
        nome="Maionese Artesanal de Ervas",
        preco=Decimal("3.00"),
    )
    adicional_bacon = ProdutoAdicional(
        produto_id=produto.id,
        nome="Maionese Artesanal de Bacon",
        preco=Decimal("3.00"),
    )
    cliente = Cliente(
        nome="Cliente Teste",
        telefone="61999990001",
        email="cliente.teste@paraibahotdog.com",
        pontos_fidelidade=0,
        ativo=True,
    )
    db_session.add_all([variacao, adicional_ervas, adicional_bacon, cliente])
    db_session.commit()

    return {
        "unidade": unidade,
        "produto": produto,
        "variacao": variacao,
        "adicionais": [adicional_ervas, adicional_bacon],
        "cliente": cliente,
    }


@pytest.mark.integration
def test_criar_pagar_e_manter_item_na_cozinha(cliente, cardapio_base):
    """Garante criacao, pagamento e exibicao do item na cozinha."""
    payload = {
        "unidade_id": cardapio_base["unidade"].id,
        "nome_comanda": "Daniel",
        "cliente_id": cardapio_base["cliente"].id,
        "observacao": "Pago no caixa",
        "itens": [
            {
                "produto_variacao_id": cardapio_base["variacao"].id,
                "quantidade": 2,
                "observacao": "Sem milho",
                "adicional_ids": [adicional.id for adicional in cardapio_base["adicionais"]],
            }
        ],
    }

    resposta_pedido = cliente.post("/pedidos/", json=payload)
    assert resposta_pedido.status_code == 201
    pedido = resposta_pedido.json()
    assert pedido["status"] == "aberto"
    assert pedido["total"] == "51.80"
    assert pedido["itens"][0]["produto_nome"] == "Tradicional"
    assert pedido["itens"][0]["produto_variacao_nome"] == "Tradicional"

    resposta_pagamento = cliente.post(
        f"/pedidos/{pedido['id']}/finalizar",
        json={"forma_pagamento": "pix"},
    )
    assert resposta_pagamento.status_code == 200
    pedido_pago = resposta_pagamento.json()
    assert pedido_pago["status"] == "pago"
    assert pedido_pago["pontos_fidelidade_creditados"] is True

    resposta_cozinha = cliente.get(
        f"/pedidos/cozinha?unidade_id={cardapio_base['unidade'].id}"
    )
    assert resposta_cozinha.status_code == 200
    cozinha = resposta_cozinha.json()
    assert len(cozinha) == 1
    assert cozinha[0]["pedido_id"] == pedido["id"]
    assert cozinha[0]["nome_comanda"] == "Daniel"
    assert cozinha[0]["quantidade"] == 2

    resposta_cliente = cliente.get(f"/clientes/{cardapio_base['cliente'].id}")
    assert resposta_cliente.status_code == 200
    assert resposta_cliente.json()["pontos_fidelidade"] == 2


@pytest.mark.integration
def test_resgate_fidelidade_aplica_desconto_e_debita_pontos_no_pagamento(cliente, cardapio_base):
    """Garante aplicacao e baixa de pontos no desconto fidelidade."""
    cardapio_base["cliente"].pontos_fidelidade = 10

    resposta_pedido = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": cardapio_base["unidade"].id,
            "nome_comanda": "Cliente Fidelidade",
            "cliente_id": cardapio_base["cliente"].id,
            "usar_desconto_fidelidade": True,
            "itens": [
                {
                    "produto_variacao_id": cardapio_base["variacao"].id,
                    "quantidade": 1,
                    "observacao": None,
                    "adicional_ids": [],
                }
            ],
        },
    )
    assert resposta_pedido.status_code == 201
    pedido = resposta_pedido.json()
    assert pedido["subtotal"] == "19.90"
    assert pedido["desconto_fidelidade"] == "17.00"
    assert pedido["total"] == "2.90"
    assert pedido["pontos_fidelidade_utilizados"] == 10

    resposta_pagamento = cliente.post(
        f"/pedidos/{pedido['id']}/finalizar",
        json={"forma_pagamento": "dinheiro"},
    )
    assert resposta_pagamento.status_code == 200

    resposta_cliente = cliente.get(f"/clientes/{cardapio_base['cliente'].id}")
    assert resposta_cliente.status_code == 200
    assert resposta_cliente.json()["pontos_fidelidade"] == 1


@pytest.mark.integration
def test_status_cozinha_atualiza_todos_os_itens_do_lote(cliente, cardapio_base):
    """Garante atualizacao em lote do status dos itens da cozinha."""
    resposta_pedido = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": cardapio_base["unidade"].id,
            "nome_comanda": "Lote Cozinha",
            "cliente_id": None,
            "itens": [
                {
                    "produto_variacao_id": cardapio_base["variacao"].id,
                    "quantidade": 1,
                    "observacao": "Sem milho",
                    "adicional_ids": [cardapio_base["adicionais"][0].id],
                },
                {
                    "produto_variacao_id": cardapio_base["variacao"].id,
                    "quantidade": 1,
                    "observacao": "Sem batata",
                    "adicional_ids": [cardapio_base["adicionais"][1].id],
                },
            ],
        },
    )
    assert resposta_pedido.status_code == 201
    pedido = resposta_pedido.json()

    resposta_status = cliente.patch(
        "/pedidos/cozinha/status",
        json={
            "pedido_id": pedido["id"],
            "lote": 1,
            "status": "preparando",
        },
    )
    assert resposta_status.status_code == 200
    itens = resposta_status.json()
    assert len(itens) == 2
    assert {item["status"] for item in itens} == {"preparando"}


@pytest.mark.integration
def test_cancelamento_parcial_divide_item(cliente, cardapio_base):
    """Garante que cancelamento parcial divide o item do pedido."""
    resposta_pedido = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": cardapio_base["unidade"].id,
            "nome_comanda": "Maria",
            "cliente_id": None,
            "observacao": None,
            "itens": [
                {
                    "produto_variacao_id": cardapio_base["variacao"].id,
                    "quantidade": 4,
                    "observacao": None,
                    "adicional_ids": [],
                }
            ],
        },
    )
    assert resposta_pedido.status_code == 201
    pedido = resposta_pedido.json()
    item_id = pedido["itens"][0]["id"]

    resposta_cancelar = cliente.post(
        f"/pedidos/itens/{item_id}/cancelar",
        json={
            "quantidade": 1,
            "motivo_cancelamento": "Cliente desistiu de uma unidade",
        },
    )
    assert resposta_cancelar.status_code == 200
    itens = resposta_cancelar.json()["itens"]

    item_ativo = next(item for item in itens if item["status"] == "aberto")
    item_cancelado = next(
        item for item in itens if item["status"] == "cancelado")
    assert item_ativo["quantidade"] == 3
    assert item_cancelado["quantidade"] == 1
    assert item_cancelado["motivo_cancelamento"] == "Cliente desistiu de uma unidade"


@pytest.mark.integration
def test_para_viagem_pedido_e_cozinha(cliente, cardapio_base):
    """Garante criacao, atualizacao e exibicao do marcador para_viagem na cozinha."""
    unidade_id = cardapio_base["unidade"].id
    variacao_id = cardapio_base["variacao"].id

    resposta_criacao = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": unidade_id,
            "nome_comanda": "Viagem 1",
            "cliente_id": None,
            "observacao": None,
            "para_viagem": True,
            "itens": [
                {
                    "produto_variacao_id": variacao_id,
                    "quantidade": 1,
                    "observacao": None,
                    "adicional_ids": [],
                }
            ],
        },
    )
    assert resposta_criacao.status_code == 201
    pedido = resposta_criacao.json()
    assert pedido["para_viagem"] is True

    cozinha = cliente.get(f"/pedidos/cozinha?unidade_id={unidade_id}").json()
    assert len(cozinha) == 1
    assert cozinha[0]["para_viagem"] is True

    resposta_patch = cliente.patch(
        f"/pedidos/{pedido['id']}/para-viagem",
        json={"para_viagem": False},
    )
    assert resposta_patch.status_code == 200
    assert resposta_patch.json()["para_viagem"] is False

    cozinha_atualizada = cliente.get(f"/pedidos/cozinha?unidade_id={unidade_id}").json()
    assert cozinha_atualizada[0]["para_viagem"] is False

    cliente.post(
        f"/pedidos/{pedido['id']}/cancelar",
        json={"motivo_cancelamento": "Teste cancelamento"},
    )
    resposta_cancelado = cliente.patch(
        f"/pedidos/{pedido['id']}/para-viagem",
        json={"para_viagem": True},
    )
    assert resposta_cancelado.status_code == 400


@pytest.mark.integration
def test_adicionar_itens_em_pedido_aberto_soma_subtotal_sem_duplicar(cliente, cardapio_base):
    """Garante que novos lotes adicionados entram uma unica vez no subtotal e no total."""
    unidade_id = cardapio_base["unidade"].id
    variacao_id = cardapio_base["variacao"].id

    criacao = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": unidade_id,
            "nome_comanda": "Lote Extra",
            "itens": [{"produto_variacao_id": variacao_id, "quantidade": 1, "adicional_ids": []}],
        },
    )
    assert criacao.status_code == 201
    pedido_id = criacao.json()["id"]

    adicao = cliente.post(
        f"/pedidos/{pedido_id}/itens",
        json={
            "itens": [{"produto_variacao_id": variacao_id, "quantidade": 1, "adicional_ids": []}],
        },
    )
    assert adicao.status_code == 200
    dados = adicao.json()
    assert len(dados["itens"]) == 2
    assert dados["subtotal"] == "39.80"
    assert dados["total"] == "39.80"


@pytest.mark.integration
def test_acrescimo_combo_entra_no_total_salvo(cliente, db_session, cardapio_base):
    """Garante que o adicional de produto no combo e validado e somado no servidor."""
    bebida_combo = Produto(
        nome="Suco Del Valle Uva",
        descricao="Lata 290ml",
        ativo=True,
        disponivel_no_combo=True,
        valor_adicional_combo=Decimal("3.00"),
        disponivel_todas_unidades=True,
        subcategoria_id=cardapio_base["produto"].subcategoria_id,
    )
    produto_fora_combo = Produto(
        nome="Item Fora do Combo",
        descricao="Nao elegivel",
        ativo=True,
        disponivel_no_combo=False,
        valor_adicional_combo=Decimal("5.00"),
        disponivel_todas_unidades=True,
        subcategoria_id=cardapio_base["produto"].subcategoria_id,
    )
    db_session.add_all([bebida_combo, produto_fora_combo])
    db_session.commit()

    resposta = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": cardapio_base["unidade"].id,
            "nome_comanda": "Combo com Suco",
            "itens": [
                {
                    "produto_variacao_id": cardapio_base["variacao"].id,
                    "quantidade": 2,
                    "observacao": "Combo: Batata Chips + Suco Del Valle Uva",
                    "adicional_ids": [],
                    "combo_produto_ids": [bebida_combo.id],
                }
            ],
        },
    )
    assert resposta.status_code == 201
    dados = resposta.json()
    assert dados["itens"][0]["preco_unitario"] == "22.90"
    assert dados["subtotal"] == "45.80"
    assert dados["total"] == "45.80"

    invalido = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": cardapio_base["unidade"].id,
            "nome_comanda": "Combo Invalido",
            "itens": [
                {
                    "produto_variacao_id": cardapio_base["variacao"].id,
                    "quantidade": 1,
                    "adicional_ids": [],
                    "combo_produto_ids": [produto_fora_combo.id],
                }
            ],
        },
    )
    assert invalido.status_code == 400


@pytest.mark.integration
def test_nao_permite_alterar_nem_reabrir_pedido_pago(cliente, cardapio_base):
    """Garante que pedidos ja pagos nao podem receber, aumentar, editar ou cancelar itens."""
    unidade_id = cardapio_base["unidade"].id
    variacao_id = cardapio_base["variacao"].id

    criacao = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": unidade_id,
            "nome_comanda": "Pedido Pago",
            "cliente_id": cardapio_base["cliente"].id,
            "itens": [{"produto_variacao_id": variacao_id, "quantidade": 1, "adicional_ids": []}],
        },
    )
    assert criacao.status_code == 201
    pedido_id = criacao.json()["id"]
    item_id = criacao.json()["itens"][0]["id"]

    assert cliente.post(f"/pedidos/{pedido_id}/finalizar", json={"forma_pagamento": "pix"}).status_code == 200

    assert (
        cliente.post(
            f"/pedidos/{pedido_id}/itens",
            json={"itens": [{"produto_variacao_id": variacao_id, "quantidade": 1, "adicional_ids": []}]},
        ).status_code
        == 400
    )
    assert cliente.post(f"/pedidos/itens/{item_id}/aumentar", json={"quantidade": 1}).status_code == 400
    assert (
        cliente.post(
            f"/pedidos/itens/{item_id}/cancelar",
            json={"motivo_cancelamento": "Tentativa"},
        ).status_code
        == 400
    )
    assert cliente.patch(f"/pedidos/itens/{item_id}", json={"observacao": "Sem milho"}).status_code == 400

    pedido_atual = cliente.get(f"/pedidos/{pedido_id}").json()
    assert pedido_atual["status"] == "pago"
    assert len(pedido_atual["itens"]) == 1


@pytest.mark.integration
def test_atualizar_observacao_item_aberto(cliente, cardapio_base):
    """Garante edicao de observacao de item aberto antes do preparo e bloqueio apos preparo."""
    unidade_id = cardapio_base["unidade"].id
    variacao_id = cardapio_base["variacao"].id

    criacao = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": unidade_id,
            "nome_comanda": "Editar Obs",
            "itens": [
                {
                    "produto_variacao_id": variacao_id,
                    "quantidade": 1,
                    "observacao": "Maionese: Ervas",
                    "adicional_ids": [],
                }
            ],
        },
    )
    assert criacao.status_code == 201
    pedido_id = criacao.json()["id"]
    item_id = criacao.json()["itens"][0]["id"]

    atualizacao = cliente.patch(
        f"/pedidos/itens/{item_id}",
        json={"observacao": "Maionese: Ervas\nObs: sem cebola"},
    )
    assert atualizacao.status_code == 200
    assert atualizacao.json()["itens"][0]["observacao"] == "Maionese: Ervas\nObs: sem cebola"

    cliente.patch("/pedidos/cozinha/status", json={"pedido_id": pedido_id, "lote": 1, "status": "preparando"})
    bloqueado = cliente.patch(f"/pedidos/itens/{item_id}", json={"observacao": "Obs: tarde demais"})
    assert bloqueado.status_code == 400


@pytest.mark.integration
def test_atualizar_status_cozinha_trava_apenas_tabela_pedidos_no_postgres(cliente, db_session, cardapio_base):
    """Garante FOR UPDATE OF pedidos para nao falhar com LEFT OUTER JOIN no PostgreSQL."""
    from sqlalchemy.dialects import postgresql  # pylint: disable=import-outside-toplevel

    from src.pedidos import repository  # pylint: disable=import-outside-toplevel
    from src.pedidos.schema import AtualizarStatusCozinha  # pylint: disable=import-outside-toplevel
    from src.pedidos.model import StatusItemPedido  # pylint: disable=import-outside-toplevel

    criacao = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": cardapio_base["unidade"].id,
            "nome_comanda": "Teste Postgres Lock",
            "itens": [
                {
                    "produto_variacao_id": cardapio_base["variacao"].id,
                    "quantidade": 1,
                    "adicional_ids": [],
                }
            ],
        },
    )
    assert criacao.status_code == 201
    pedido_id = criacao.json()["id"]

    sqls_postgres: list[str] = []
    query_original = db_session.query

    class QueryEspiada:
        """Proxy simples para inspecionar o SQL compilado para PostgreSQL em tempo de execucao."""

        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, nome):
            attr = getattr(self._inner, nome)
            if not callable(attr):
                return attr

            def wrapper(*args, **kwargs):
                res = attr(*args, **kwargs)
                if hasattr(res, "statement"):
                    return QueryEspiada(res)
                return res

            return wrapper

        def first(self):
            sqls_postgres.append(str(self._inner.statement.compile(dialect=postgresql.dialect())))
            return self._inner.first()

    db_session.query = lambda *args, **kwargs: QueryEspiada(query_original(*args, **kwargs))
    try:
        itens = repository.atualizar_status_cozinha(
            db_session,
            AtualizarStatusCozinha(pedido_id=pedido_id, lote=1, status=StatusItemPedido.entregue),
        )
    finally:
        db_session.query = query_original

    assert len(itens) == 1
    assert itens[0].status == StatusItemPedido.entregue
    assert any("FOR UPDATE OF pedidos" in sql for sql in sqls_postgres)


@pytest.mark.integration
def test_criar_pedido_ja_finalizado_em_uma_requisicao(cliente, cardapio_base):
    """Garante criacao e pagamento atomicos em POST /pedidos/ com forma_pagamento e fidelidade."""
    cardapio_base["cliente"].pontos_fidelidade = 10

    resposta = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": cardapio_base["unidade"].id,
            "nome_comanda": "Pagamento Direto",
            "cliente_id": cardapio_base["cliente"].id,
            "usar_desconto_fidelidade": True,
            "forma_pagamento": "pix",
            "itens": [
                {
                    "produto_variacao_id": cardapio_base["variacao"].id,
                    "quantidade": 2,
                    "adicional_ids": [],
                }
            ],
        },
    )
    assert resposta.status_code == 201
    dados = resposta.json()
    assert dados["status"] == "pago"
    assert dados["forma_pagamento"] == "pix"
    assert dados["fechado_em"] is not None
    assert dados["subtotal"] == "39.80"
    assert dados["desconto_fidelidade"] == "17.00"
    assert dados["total"] == "22.80"
    assert dados["pontos_fidelidade_utilizados"] == 10
    assert dados["pontos_fidelidade_creditados"] is True

    resposta_cliente = cliente.get(f"/clientes/{cardapio_base['cliente'].id}")
    assert resposta_cliente.status_code == 200
    assert resposta_cliente.json()["pontos_fidelidade"] == 2

    sem_itens = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": cardapio_base["unidade"].id,
            "nome_comanda": "Sem Itens",
            "forma_pagamento": "pix",
            "itens": [],
        },
    )
    assert sem_itens.status_code == 400


@pytest.mark.integration
def test_listar_pedidos_apenas_hoje_ou_abertos(cliente, db_session, cardapio_base):
    """Garante que apenas_hoje_ou_abertos mantem abertos antigos e oculta pagos antigos."""
    from datetime import datetime, timedelta  # pylint: disable=import-outside-toplevel

    from src.pedidos.model import Pedido, StatusPedido  # pylint: disable=import-outside-toplevel

    antigo = datetime.utcnow() - timedelta(days=3)
    unidade_id = cardapio_base["unidade"].id

    aberto_antigo = Pedido(
        unidade_id=unidade_id,
        nome_comanda="Aberto Antigo",
        status=StatusPedido.aberto,
        created_at=antigo,
    )
    pago_antigo = Pedido(
        unidade_id=unidade_id,
        nome_comanda="Pago Antigo",
        status=StatusPedido.pago,
        created_at=antigo,
    )
    db_session.add_all([aberto_antigo, pago_antigo])
    db_session.commit()

    pago_hoje = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": unidade_id,
            "nome_comanda": "Pago Hoje",
            "forma_pagamento": "pix",
            "itens": [
                {
                    "produto_variacao_id": cardapio_base["variacao"].id,
                    "quantidade": 1,
                    "adicional_ids": [],
                }
            ],
        },
    )
    assert pago_hoje.status_code == 201

    filtrados = cliente.get(
        "/pedidos/",
        params={"unidade_id": unidade_id, "apenas_hoje_ou_abertos": True},
    )
    assert filtrados.status_code == 200
    nomes = {pedido["nome_comanda"] for pedido in filtrados.json()}
    assert "Aberto Antigo" in nomes
    assert "Pago Hoje" in nomes
    assert "Pago Antigo" not in nomes


@pytest.mark.integration
def test_listagens_nao_disparam_cascata_de_catalogo(cliente, db_session, cardapio_base):
    """Garante que listar pedidos e fila da cozinha nao consultam catalogo ou unidades."""
    from sqlalchemy import event  # pylint: disable=import-outside-toplevel

    resposta = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": cardapio_base["unidade"].id,
            "nome_comanda": "Sem Cascata",
            "cliente_id": cardapio_base["cliente"].id,
            "itens": [
                {
                    "produto_variacao_id": cardapio_base["variacao"].id,
                    "quantidade": 1,
                    "adicional_ids": [cardapio_base["adicionais"][0].id],
                }
            ],
        },
    )
    assert resposta.status_code == 201
    unidade_id = cardapio_base["unidade"].id
    db_session.expire_all()

    sqls: list[str] = []

    def capturar(_conn, _cursor, statement, _parameters, _context, _executemany):
        sqls.append(statement.lower())

    event.listen(test_engine, "before_cursor_execute", capturar)
    try:
        res_pedidos = cliente.get("/pedidos/", params={"unidade_id": unidade_id})
        res_cozinha = cliente.get("/pedidos/cozinha", params={"unidade_id": unidade_id})
    finally:
        event.remove(test_engine, "before_cursor_execute", capturar)

    assert res_pedidos.status_code == 200
    assert res_cozinha.status_code == 200
    tabelas_proibidas = ("produtos", "grupos_opcoes", "opcoes_complemento", "unidades", "enderecos", "clientes")
    for sql in sqls:
        for tabela in tabelas_proibidas:
            assert tabela not in sql, f"Consulta inesperada na tabela {tabela}: {sql}"
