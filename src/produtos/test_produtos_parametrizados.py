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


@pytest.mark.parametrize(
    "rota, dados_requisicao, status_esperado",
    [
        # 201 Created: Criacao com sucesso de produtos com dados validos.
        (
            "/produtos/variacoes",
            {"nome": "Tradicional Duplo", "tipo": "normal", "preco": 23.90},
            201,
        ),
        (
            "/produtos/adicionais",
            {"nome": "Maionese Artesanal de Bacon", "preco": 3.00},
            201,
        ),
        # 422 Unprocessable Entity: Validacao de erros (precos negativos, campos obrigatorios ausentes).
        (
            "/produtos/variacoes",
            {"nome": "Combo Tradicional", "tipo": "combo", "preco": -32.90},
            422,
        ),
        (
            "/produtos/adicionais",
            {"nome": "Maionese Invalida", "preco": -3.00},
            422,
        ),
        (
            "/produtos/variacoes",
            {"nome": "Combo Tradicional", "preco": 32.90},
            422,
        ),
        (
            "/produtos/adicionais",
            {"preco": 5.00},
            422,
        ),
    ],
)
def test_criar_itens(cliente, dados_base, rota, dados_requisicao, status_esperado):
    """Garante criacao e validacao de variacoes e adicionais."""
    # Injeta ID do produto para manter a integridade referencial.
    if "produto_id" not in dados_requisicao:
        dados_requisicao["produto_id"] = dados_base["produto"]["id"]

    resposta = cliente.post(rota, json=dados_requisicao)
    assert resposta.status_code == status_esperado


@pytest.mark.parametrize(
    "rota, status_esperado",
    [
        # 200 OK: Listagem e leitura de produtos, variacoes e adicionais.
        ("/produtos/", 200),
        ("/produtos/categorias", 200),
        ("/produtos/subcategorias", 200),
        ("/produtos/variacoes", 200),
        ("/produtos/adicionais", 200),
        ("/produtos/{produto_id}", 200),
        # 404 Not Found: IDs que nao existem no banco.
        ("/produtos/99999", 404),
    ],
)
def test_ler_itens(cliente, dados_base, rota, status_esperado):
    """Garante leitura de endpoints de produtos e itens relacionados."""
    if "{produto_id}" in rota:
        rota = rota.format(produto_id=dados_base["produto"]["id"])

    resposta = cliente.get(rota)
    assert resposta.status_code == status_esperado
