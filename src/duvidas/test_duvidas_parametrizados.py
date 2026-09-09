"""Testes parametrizados dos endpoints de duvidas frequentes."""

# Pylint doesn't understand pytest fixtures in this module.
# pylint: disable=redefined-outer-name,unused-argument

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.duvidas.model import DuvidaFrequente
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
    """Cria uma sessao SQLite isolada para cada teste de duvidas."""
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
def duvida_valida(db_session):
    """Cria uma duvida valida no banco de testes."""
    duvida = DuvidaFrequente(
        pergunta="Pergunta Inicial?",
        resposta="Resposta Inicial",
        ordem=0,
        ativo=True,
    )
    db_session.add(duvida)
    db_session.commit()
    db_session.refresh(duvida)
    return duvida


@pytest.fixture
def unauthenticated_user():
    """Remove o usuario autenticado fake para simular requisicao sem token."""
    app.dependency_overrides.pop(get_current_user, None)
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def non_admin_user():
    """Simula um usuario autenticado com role diferente de administrador."""

    def _get_user():
        return {
            "sub": "user-cliente",
            "preferred_username": "cliente",
            "email": "cliente@example.com",
            "roles": ["cliente"],
        }

    app.dependency_overrides[get_current_user] = _get_user
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize(
    "payload",
    [
        {"pergunta": "", "resposta": "Resp"},
        {"pergunta": "   ", "resposta": "Resp"},
        {"pergunta": "a" * 256, "resposta": "Resp"},
        {"resposta": "Sem pergunta"},
        {"pergunta": "Pergunta?", "resposta": ""},
        {"pergunta": "Pergunta?", "resposta": "   "},
        {"pergunta": "Pergunta?"},
        {"pergunta": "Pergunta?", "resposta": "Resp", "ordem": -1},
    ],
)
def test_criar_duvida_invalida_retorna_422(override_get_db, payload):
    """Garante retorno 422 para payloads invalidos no cadastro de duvidas."""
    response = client.post("/duvidas/", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"pergunta": ""},
        {"pergunta": "   "},
        {"pergunta": "a" * 256},
        {"resposta": ""},
        {"resposta": "   "},
        {"ordem": -1},
    ],
)
def test_atualizar_duvida_invalida_retorna_422(override_get_db, duvida_valida, payload):
    """Garante retorno 422 para atualizacoes com dados invalidos."""
    response = client.patch(f"/duvidas/{duvida_valida.id}", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("metodo", ["post", "patch", "delete"])
def test_rotas_protegidas_sem_autenticacao_retornam_401(
    override_get_db, unauthenticated_user, duvida_valida, metodo
):
    """Garante retorno 401 para rotas de mutacao de duvidas sem token de autenticacao."""
    if metodo == "post":
        response = client.post("/duvidas/", json={"pergunta": "Nova?", "resposta": "Sim"})
    elif metodo == "patch":
        response = client.patch(f"/duvidas/{duvida_valida.id}", json={"ordem": 10})
    else:
        response = client.delete(f"/duvidas/{duvida_valida.id}")

    assert response.status_code == 401


@pytest.mark.parametrize("metodo", ["post", "patch", "delete"])
def test_rotas_protegidas_usuario_sem_role_admin_retornam_403(
    override_get_db, non_admin_user, duvida_valida, metodo
):
    """Garante retorno 403 para usuarios autenticados sem perfil administrador."""
    if metodo == "post":
        response = client.post("/duvidas/", json={"pergunta": "Nova?", "resposta": "Sim"})
    elif metodo == "patch":
        response = client.patch(f"/duvidas/{duvida_valida.id}", json={"ordem": 10})
    else:
        response = client.delete(f"/duvidas/{duvida_valida.id}")

    assert response.status_code == 403
    assert response.json()["detail"] == "Usuario sem permissao para acessar este recurso"


def test_rotas_publicas_sem_autenticacao_retornam_200(
    override_get_db, unauthenticated_user, duvida_valida
):
    """Garante que a listagem e a consulta por ID sao acessiveis sem token."""
    resp_listar = client.get("/duvidas/")
    assert resp_listar.status_code == 200
    assert len(resp_listar.json()) == 1

    resp_obter = client.get(f"/duvidas/{duvida_valida.id}")
    assert resp_obter.status_code == 200
    assert resp_obter.json()["id"] == duvida_valida.id

