"""Testes de integracao dos endpoints de duvidas frequentes com TestClient."""

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
    """Cria uma duvida frequente valida no banco de testes."""
    duvida = DuvidaFrequente(
        pergunta="Quais são os horários de funcionamento?",
        resposta="Funcionamos todos os dias, das 17:00 às 23:00",
        ordem=0,
        ativo=True,
    )
    db_session.add(duvida)
    db_session.commit()
    db_session.refresh(duvida)
    return duvida


def test_listar_duvidas_vazio(override_get_db):
    """Garante que a listagem de duvidas vazia retorna lista vazia com status 200."""
    response = client.get("/duvidas/")
    assert response.status_code == 200
    assert response.json() == []


def test_criar_duvida_sucesso(override_get_db):
    """Garante que um administrador consegue cadastrar uma duvida frequente."""
    payload = {
        "pergunta": "Vocês fazem delivery?",
        "resposta": "Sim, fazemos delivery pelo iFood",
        "ordem": 1,
        "ativo": True,
    }
    response = client.post("/duvidas/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["pergunta"] == payload["pergunta"]
    assert data["resposta"] == payload["resposta"]
    assert data["ordem"] == 1
    assert data["ativo"] is True


def test_obter_duvida_por_id(override_get_db, duvida_valida):
    """Garante que uma duvida pode ser consultada pelo ID."""
    response = client.get(f"/duvidas/{duvida_valida.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == duvida_valida.id
    assert data["pergunta"] == duvida_valida.pergunta
    assert data["resposta"] == duvida_valida.resposta


def test_obter_duvida_inexistente_retorna_404(override_get_db):
    """Garante 404 ao buscar uma duvida inexistente."""
    response = client.get("/duvidas/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Duvida nao encontrada"


def test_listar_duvidas_filtra_apenas_ativas_por_padrao(override_get_db, db_session):
    """Garante que a listagem publica traz apenas duvidas ativas, ordenadas por ordem e id."""
    d1 = DuvidaFrequente(pergunta="Duvida B (ordem 2)", resposta="Resp B", ordem=2, ativo=True)
    d2 = DuvidaFrequente(pergunta="Duvida Inativa", resposta="Resp Inativa", ordem=1, ativo=False)
    d3 = DuvidaFrequente(pergunta="Duvida A (ordem 0)", resposta="Resp A", ordem=0, ativo=True)
    db_session.add_all([d1, d2, d3])
    db_session.commit()

    response = client.get("/duvidas/")
    assert response.status_code == 200
    itens = response.json()
    assert len(itens) == 2
    assert itens[0]["pergunta"] == "Duvida A (ordem 0)"
    assert itens[1]["pergunta"] == "Duvida B (ordem 2)"


def test_listar_duvidas_inclui_inativas_quando_solicitado(override_get_db, db_session):
    """Garante que o admin pode solicitar apenas_ativas=false e ver as inativas."""
    d1 = DuvidaFrequente(pergunta="Duvida Ativa", resposta="Resp", ordem=1, ativo=True)
    d2 = DuvidaFrequente(pergunta="Duvida Oculta", resposta="Resp", ordem=0, ativo=False)
    db_session.add_all([d1, d2])
    db_session.commit()

    response = client.get("/duvidas/?apenas_ativas=false")
    assert response.status_code == 200
    itens = response.json()
    assert len(itens) == 2
    assert itens[0]["pergunta"] == "Duvida Oculta"
    assert itens[0]["ativo"] is False
    assert itens[1]["pergunta"] == "Duvida Ativa"
    assert itens[1]["ativo"] is True


def test_listar_duvidas_paginacao(override_get_db, db_session):
    """Garante paginacao correta com skip e limit."""
    duvidas = [
        DuvidaFrequente(pergunta=f"Pergunta {i}", resposta=f"Resposta {i}", ordem=i, ativo=True)
        for i in range(5)
    ]
    db_session.add_all(duvidas)
    db_session.commit()

    response = client.get("/duvidas/?skip=1&limit=2")
    assert response.status_code == 200
    itens = response.json()
    assert len(itens) == 2
    assert itens[0]["pergunta"] == "Pergunta 1"
    assert itens[1]["pergunta"] == "Pergunta 2"


def test_atualizar_duvida_completa(override_get_db, duvida_valida):
    """Garante atualizacao completa dos campos de uma duvida."""
    payload = {
        "pergunta": "Pergunta Atualizada?",
        "resposta": "Resposta Atualizada",
        "ordem": 10,
        "ativo": False,
    }
    response = client.patch(f"/duvidas/{duvida_valida.id}", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["pergunta"] == "Pergunta Atualizada?"
    assert data["resposta"] == "Resposta Atualizada"
    assert data["ordem"] == 10
    assert data["ativo"] is False


def test_atualizar_duvida_parcial_apenas_ordem(override_get_db, duvida_valida):
    """Garante atualizacao parcial enviando apenas a ordem (reordenacao no admin)."""
    response = client.patch(f"/duvidas/{duvida_valida.id}", json={"ordem": 5})
    assert response.status_code == 200
    data = response.json()
    assert data["ordem"] == 5
    assert data["pergunta"] == duvida_valida.pergunta
    assert data["resposta"] == duvida_valida.resposta
    assert data["ativo"] is True


def test_atualizar_duvida_parcial_apenas_ativo(override_get_db, duvida_valida):
    """Garante atualizacao parcial enviando apenas o status de visibilidade."""
    response = client.patch(f"/duvidas/{duvida_valida.id}", json={"ativo": False})
    assert response.status_code == 200
    data = response.json()
    assert data["ativo"] is False
    assert data["pergunta"] == duvida_valida.pergunta


def test_atualizar_duvida_inexistente_retorna_404(override_get_db):
    """Garante 404 ao tentar atualizar uma duvida que nao existe."""
    response = client.patch("/duvidas/99999", json={"ordem": 1})
    assert response.status_code == 404
    assert response.json()["detail"] == "Duvida nao encontrada"


def test_excluir_duvida_sucesso(override_get_db, duvida_valida):
    """Garante exclusao de duvida com status 204 e 404 em consulta subsequente."""
    response = client.delete(f"/duvidas/{duvida_valida.id}")
    assert response.status_code == 204

    consulta = client.get(f"/duvidas/{duvida_valida.id}")
    assert consulta.status_code == 404


def test_excluir_duvida_inexistente_retorna_404(override_get_db):
    """Garante 404 ao tentar excluir uma duvida inexistente."""
    response = client.delete("/duvidas/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Duvida nao encontrada"

