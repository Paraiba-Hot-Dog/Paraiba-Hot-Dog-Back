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
    cardapio_base["cliente"].pontos_fidelidade = 12

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
    assert pedido["pontos_fidelidade_utilizados"] == 12

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
