"""Testes de integracao local dos endpoints de avaliacoes com TestClient."""

# Pylint doesn't understand pytest fixtures in this module.
# pylint: disable=redefined-outer-name,unused-argument

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.avaliacoes import repository
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
def avaliacao_valida(db_session):
    """Cria uma avaliacao exibida para os cenarios de leitura e escrita."""
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


@pytest.fixture
def avaliacao_oculta(db_session):
    """Cria uma avaliacao oculta do site."""
    avaliacao = Avaliacao(
        nome_cliente="Joao Souza",
        descricao="Demorou um pouco, mas valeu a pena.",
        estrelas=3,
        ativo=False,
    )
    db_session.add(avaliacao)
    db_session.commit()
    db_session.refresh(avaliacao)
    return avaliacao


def test_listar_vazio(override_get_db):
    """Garante que a listagem vazia retorna lista vazia."""
    response = client.get("/avaliacoes")
    assert response.status_code == 200
    assert response.json() == []


def test_listar_apenas_ativas_por_padrao(override_get_db, avaliacao_valida, avaliacao_oculta):
    """Garante que a listagem padrao retorna somente avaliacoes exibidas."""
    response = client.get("/avaliacoes")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["nome_cliente"] == "Maria Silva"
    assert items[0]["ativo"] is True


def test_listar_ocultas_com_filtro(override_get_db, avaliacao_valida, avaliacao_oculta):
    """Garante que o filtro ativo=false retorna apenas as ocultas."""
    response = client.get("/avaliacoes?ativo=false")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["nome_cliente"] == "Joao Souza"
    assert items[0]["ativo"] is False


def test_listar_paginacao(override_get_db, db_session):
    """Garante que skip e limit paginam o resultado."""
    for i in range(5):
        db_session.add(
            Avaliacao(
                nome_cliente=f"Cliente {i}",
                descricao=f"Comentario {i}",
                estrelas=4,
                ativo=True,
            )
        )
    db_session.commit()

    response = client.get("/avaliacoes?skip=1&limit=2")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_criar_avaliacao(override_get_db, authenticated_user):
    """Garante criacao de avaliacao autenticada com ativo=true por padrao."""
    payload = {
        "nome_cliente": "Ana Lima",
        "descricao": "Atendimento nota 10.",
        "estrelas": 5,
    }
    response = client.post("/avaliacoes", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["nome_cliente"] == "Ana Lima"
    assert data["estrelas"] == 5
    assert data["ativo"] is True
    assert "id" in data


def test_atualizar_visibilidade(override_get_db, authenticated_user, avaliacao_valida):
    """Garante que o PATCH altera somente a visibilidade quando so ativo e enviado."""
    response = client.patch(
        f"/avaliacoes/{avaliacao_valida.id}", json={"ativo": False}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ativo"] is False
    assert data["nome_cliente"] == "Maria Silva"
    assert data["descricao"] == "Melhor cachorro-quente da Paraiba!"
    assert data["estrelas"] == 5


def test_atualizar_demais_atributos(override_get_db, authenticated_user, avaliacao_valida):
    """Garante que o PATCH altera nome, descricao e estrelas."""
    payload = {
        "nome_cliente": "Maria S. Costa",
        "descricao": "Voltei e continua otimo.",
        "estrelas": 4,
    }
    response = client.patch(f"/avaliacoes/{avaliacao_valida.id}", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["nome_cliente"] == "Maria S. Costa"
    assert data["descricao"] == "Voltei e continua otimo."
    assert data["estrelas"] == 4
    assert data["ativo"] is True


def test_atualizar_corpo_vazio_nao_altera(override_get_db, authenticated_user, avaliacao_valida):
    """Garante que um PATCH sem campos preserva a avaliacao."""
    response = client.patch(f"/avaliacoes/{avaliacao_valida.id}", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["nome_cliente"] == "Maria Silva"
    assert data["descricao"] == "Melhor cachorro-quente da Paraiba!"
    assert data["estrelas"] == 5
    assert data["ativo"] is True


def test_atualizar_inexistente_retorna_404(override_get_db, authenticated_user):
    """Garante 404 ao atualizar avaliacao inexistente."""
    response = client.patch("/avaliacoes/999", json={"ativo": False})
    assert response.status_code == 404
    assert response.json()["detail"] == "Avaliacao nao encontrada"


def test_excluir_avaliacao(override_get_db, authenticated_user, avaliacao_valida):
    """Garante exclusao permanente de avaliacao autenticada."""
    response = client.delete(f"/avaliacoes/{avaliacao_valida.id}")
    assert response.status_code == 204

    listagem = client.get("/avaliacoes")
    assert listagem.json() == []


def test_excluir_inexistente_retorna_404(override_get_db, authenticated_user):
    """Garante 404 ao excluir avaliacao inexistente."""
    response = client.delete("/avaliacoes/999")
    assert response.status_code == 404


def test_listar_sem_filtro_retorna_todas(db_session, avaliacao_valida, avaliacao_oculta):
    """Cobre o repositorio quando ativo e None (retorna ativas e ocultas)."""
    resultado = repository.listar_avaliacoes(db_session, ativo=None)
    assert len(resultado) == 2
