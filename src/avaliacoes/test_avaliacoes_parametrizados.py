"""Testes parametrizados dos endpoints de avaliacoes."""

# Pylint doesn't understand pytest fixtures in this module.
# pylint: disable=redefined-outer-name,unused-argument

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.avaliacoes.model import Avaliacao
from src.database import Base, get_db
from src.main import app
from src.security import get_current_user

client = TestClient(app)

TEST_DATABASE_URL = "sqlite+pysqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """Cria uma sessao SQLite isolada para cada teste de avaliacao."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
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
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_user():
    """Simula um usuario autenticado para rotas protegidas."""
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user",
        "roles": ["administrador"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def unauthenticated_user():
    """Remove o usuario autenticado para testar acesso negado."""
    app.dependency_overrides.pop(get_current_user, None)
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def avaliacao_valida(db_session):
    """Cria uma avaliacao valida para os cenarios parametrizados."""
    avaliacao = Avaliacao(
        nome_cliente="Maria Silva",
        descricao="Melhor cachorro-quente da Paraiba!",
        estrelas=5,
        ativo=True,
    )
    db_session.add(avaliacao)
    db_session.commit()
    db_session.refresh(avaliacao)
    return avaliacao


@pytest.mark.parametrize("estrelas", [1, 2, 3, 4, 5])
def test_criar_aceita_todas_as_notas(override_get_db, authenticated_user, estrelas):
    """Garante criacao de avaliacao para cada nota valida."""
    payload = {
        "nome_cliente": "Cliente Feliz",
        "descricao": "Comentario de teste.",
        "estrelas": estrelas,
    }
    response = client.post("/avaliacoes", json=payload)
    assert response.status_code == 201
    assert response.json()["estrelas"] == estrelas


@pytest.mark.parametrize(
    "payload",
    [
        {"nome_cliente": "Sem Descricao", "estrelas": 4},
        {"descricao": "Sem nome do cliente", "estrelas": 4},
        {"nome_cliente": "Sem Nota", "descricao": "Faltou a nota"},
        {"nome_cliente": "", "descricao": "Nome vazio", "estrelas": 4},
        {"nome_cliente": "Nota Zero", "descricao": "Abaixo do minimo", "estrelas": 0},
        {"nome_cliente": "Nota Seis", "descricao": "Acima do maximo", "estrelas": 6},
        {"nome_cliente": "Descricao Vazia", "descricao": "", "estrelas": 4},
        {"nome_cliente": "X" * 121, "descricao": "Nome longo demais", "estrelas": 4},
        {"nome_cliente": "Descricao Longa", "descricao": "D" * 601, "estrelas": 4},
    ],
)
def test_criar_invalido_retorna_422(override_get_db, authenticated_user, payload):
    """Garante erro de validacao para payloads invalidos na criacao."""
    response = client.post("/avaliacoes", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"estrelas": 0},
        {"estrelas": 6},
        {"nome_cliente": ""},
        {"nome_cliente": "X" * 121},
        {"descricao": ""},
        {"descricao": "D" * 601},
    ],
)
def test_atualizar_invalido_retorna_422(
    override_get_db, authenticated_user, avaliacao_valida, payload
):
    """Garante erro de validacao para payloads invalidos no PATCH."""
    response = client.patch(f"/avaliacoes/{avaliacao_valida.id}", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("nome_cliente", "Maria S. Costa"),
        ("descricao", "Atualizei meu comentario."),
        ("estrelas", 2),
        ("ativo", False),
    ],
)
def test_atualizar_campo_isolado(
    override_get_db, authenticated_user, avaliacao_valida, campo, valor
):
    """Garante que o PATCH altera cada campo isoladamente."""
    response = client.patch(f"/avaliacoes/{avaliacao_valida.id}", json={campo: valor})
    assert response.status_code == 200
    assert response.json()[campo] == valor


@pytest.mark.parametrize("limite", [600, 120])
def test_criar_aceita_limites_de_tamanho(override_get_db, authenticated_user, limite):
    """Garante que descricao com 600 e nome com 120 caracteres sao aceitos."""
    payload = {
        "nome_cliente": "N" * min(limite, 120),
        "descricao": "D" * limite,
        "estrelas": 5,
    }
    response = client.post("/avaliacoes", json=payload)
    assert response.status_code == 201


@pytest.mark.parametrize("metodo", ["post", "patch", "delete"])
def test_rotas_protegidas_sem_token_retorna_401(
    override_get_db, unauthenticated_user, avaliacao_valida, metodo
):
    """Garante 401 nas rotas protegidas sem usuario autenticado."""
    if metodo == "post":
        response = client.post(
            "/avaliacoes",
            json={
                "nome_cliente": "Cliente",
                "descricao": "Comentario.",
                "estrelas": 5,
            },
        )
    elif metodo == "patch":
        response = client.patch(
            f"/avaliacoes/{avaliacao_valida.id}", json={"ativo": False}
        )
    else:
        response = client.delete(f"/avaliacoes/{avaliacao_valida.id}")

    assert response.status_code == 401
