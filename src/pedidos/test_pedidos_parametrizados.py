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
    """Cria o TestClient usado nos cenarios parametrizados."""
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


@pytest.mark.parametrize(
    "payload, status_esperado",
    [
        (
            {
                "unidade_id": 999,
                "nome_comanda": "Unidade inexistente",
                "cliente_id": None,
                "itens": [],
            },
            404,
        ),
        (
            {
                "unidade_id": 1,
                "nome_comanda": "",
                "cliente_id": None,
                "itens": [],
            },
            422,
        ),
    ],
)
def test_validacoes_criar_pedido(cliente, cardapio_base, payload, status_esperado):
    """Garante validacoes de payload ao criar pedido."""
    if payload["unidade_id"] == 1:
        payload["unidade_id"] = cardapio_base["unidade"].id

    resposta = cliente.post("/pedidos/", json=payload)
    assert resposta.status_code == status_esperado


@pytest.mark.parametrize(
    "status_cozinha, status_esperado",
    [
        ("preparando", 200),
        ("entregue", 200),
        ("cancelado", 400),
    ],
)
def test_status_permitidos_na_cozinha(cliente, cardapio_base, status_cozinha, status_esperado):
    """Garante status permitidos e bloqueados na cozinha."""
    resposta_pedido = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": cardapio_base["unidade"].id,
            "nome_comanda": "Daniel",
            "cliente_id": None,
            "itens": [
                {
                    "produto_variacao_id": cardapio_base["variacao"].id,
                    "quantidade": 1,
                    "observacao": "Sem milho",
                    "adicional_ids": [cardapio_base["adicionais"][0].id],
                }
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
            "status": status_cozinha,
        },
    )
    assert resposta_status.status_code == status_esperado


@pytest.mark.parametrize(
    "forma_pagamento",
    ["pix", "credito", "debito", "dinheiro"],
)
def test_formas_pagamento(cliente, cardapio_base, forma_pagamento):
    """Garante finalizacao de pedido com cada forma de pagamento."""
    resposta_pedido = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": cardapio_base["unidade"].id,
            "nome_comanda": "Daniel",
            "cliente_id": cardapio_base["cliente"].id,
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

    resposta_pagamento = cliente.post(
        f"/pedidos/{resposta_pedido.json()['id']}/finalizar",
        json={"forma_pagamento": forma_pagamento},
    )
    assert resposta_pagamento.status_code == 200
    assert resposta_pagamento.json()["status"] == "pago"
    assert resposta_pagamento.json()["forma_pagamento"] == forma_pagamento


@pytest.mark.parametrize(
    "cliente_id, pontos_cliente, status_esperado",
    [
        (None, 0, 400),
        ("cliente", 11, 400),
        ("cliente", 12, 201),
    ],
)
def test_validacoes_desconto_fidelidade(
    cliente,
    cardapio_base,
    cliente_id,
    pontos_cliente,
    status_esperado,
):
    """Garante regras de uso do desconto fidelidade."""
    cardapio_base["cliente"].pontos_fidelidade = pontos_cliente
    cliente_id_payload = cardapio_base["cliente"].id if cliente_id == "cliente" else None

    resposta = cliente.post(
        "/pedidos/",
        json={
            "unidade_id": cardapio_base["unidade"].id,
            "nome_comanda": "Resgate Fidelidade",
            "cliente_id": cliente_id_payload,
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

    assert resposta.status_code == status_esperado
