import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# pylint: disable=redefined-outer-name

from src.database import Base, get_db
from src.main import app

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
    """Cria uma nova sessao de banco de dados SQLite em memoria para cada teste."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def override_get_db(db_session):
    """Substitui automaticamente a dependencia get_db do FastAPI pela sessao de teste."""

    def _get_db():
        """Fornece a sessao fake para o FastAPI durante o teste."""
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.clear()


@pytest.fixture(name="cliente")
def fixture_cliente():
    """Entrega o cliente de testes do FastAPI pronto."""
    return TestClient(app)


@pytest.fixture
def dados_base(cliente):
    """Cria categoria, subcategoria e produto base para os testes."""
    resposta_categoria = cliente.post(
        "/produtos/categorias", json={"nome": "Hot-Dog"})
    assert resposta_categoria.status_code == 201
    categoria = resposta_categoria.json()

    resposta_subcategoria = cliente.post(
        "/produtos/subcategorias",
        json={
            "nome": "Molho",
            "categoria_id": categoria["id"],
        },
    )
    assert resposta_subcategoria.status_code == 201
    subcategoria = resposta_subcategoria.json()

    resposta_produto = cliente.post(
        "/produtos/",
        json={
            "nome": "Tradicional",
            "descricao": (
                "Pao de leite Ninho, salsicha Perdigao, queijo mucarela, "
                "molho de tomate, milho e batata palha."
            ),
            "imagem_url": None,
            "ativo": True,
            "pontos_fidelidade_por_unidade": 1,
            "disponivel_todas_unidades": True,
            "subcategoria_id": subcategoria["id"],
        },
    )
    assert resposta_produto.status_code == 201
    produto = resposta_produto.json()

    return {
        "categoria": categoria,
        "subcategoria": subcategoria,
        "produto": produto,
    }


@pytest.mark.integration
def test_relacionamentos_produto(cliente, dados_base):
    """Garante variacoes e adicionais vinculados ao produto."""
    produto_id = dados_base["produto"]["id"]

    resposta_v = cliente.post(
        "/produtos/variacoes",
        json={
            "produto_id": produto_id,
            "nome": "Combo Tradicional",
            "tipo": "combo",
            "preco": 32.90,
            "ativo": True,
        },
    )
    assert resposta_v.status_code == 201

    resposta_a = cliente.post(
        "/produtos/adicionais",
        json={
            "produto_id": produto_id,
            "nome": "Maionese Artesanal de Ervas",
            "preco": 3.00,
        },
    )
    assert resposta_a.status_code == 201

    resposta_p = cliente.get(f"/produtos/{produto_id}")
    assert resposta_p.status_code == 200
    dados_produto = resposta_p.json()

    assert len(dados_produto["variacoes"]) > 0
    assert len(dados_produto["adicionais"]) > 0
    assert dados_produto["variacoes"][0]["tipo"] == "combo"
    assert dados_produto["variacoes"][0]["nome"] == "Combo Tradicional"
    assert dados_produto["adicionais"][0]["nome"] == "Maionese Artesanal de Ervas"


@pytest.mark.integration
def test_editar_categoria_e_subcategoria(cliente):
    """Garante edicao e exclusao de categoria e subcategoria."""
    resposta_categoria = cliente.post(
        "/produtos/categorias", json={"nome": "Combos"})
    assert resposta_categoria.status_code == 201
    categoria_id = resposta_categoria.json()["id"]

    resposta_categoria_update = cliente.patch(
        f"/produtos/categorias/{categoria_id}",
        json={"nome": "Combos da Bexiga"},
    )
    assert resposta_categoria_update.status_code == 200
    assert resposta_categoria_update.json()["nome"] == "Combos da Bexiga"

    resposta_subcategoria = cliente.post(
        "/produtos/subcategorias",
        json={"nome": "Promocao", "categoria_id": categoria_id},
    )
    assert resposta_subcategoria.status_code == 201
    subcategoria_id = resposta_subcategoria.json()["id"]

    resposta_subcategoria_update = cliente.patch(
        f"/produtos/subcategorias/{subcategoria_id}",
        json={"nome": "Promocao da Bexiga"},
    )
    assert resposta_subcategoria_update.status_code == 200
    assert resposta_subcategoria_update.json()["nome"] == "Promocao da Bexiga"

    resposta_excluir_categoria_vinculada = cliente.delete(
        f"/produtos/categorias/{categoria_id}"
    )
    assert resposta_excluir_categoria_vinculada.status_code == 409

    resposta_excluir_subcategoria = cliente.delete(
        f"/produtos/subcategorias/{subcategoria_id}"
    )
    assert resposta_excluir_subcategoria.status_code == 204

    resposta_excluir_categoria = cliente.delete(
        f"/produtos/categorias/{categoria_id}")
    assert resposta_excluir_categoria.status_code == 204
