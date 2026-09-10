"""Testes para os endpoints de clientes."""

# Pylint doesn't understand pytest fixtures in this module.
# pylint: disable=redefined-outer-name,unused-argument

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.clientes.model import Cliente
from src.database import Base, get_db
from src.main import app

client = TestClient(app)

TEST_DATABASE_URL = "sqlite+pysqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture(scope="function")
def db_session():
    """Cria uma nova sessao de banco de dados para cada teste."""
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
def cliente_valido(db_session):
    """Cria um cliente valido para os testes."""
    cliente = Cliente(
        nome="Maria Silva",
        telefone="83999990001",
        email="maria@email.com",
        pontos_fidelidade=3,
        ativo=True,
    )
    db_session.add(cliente)
    db_session.commit()
    db_session.refresh(cliente)
    return cliente


class TestClientes:
    """Testes para os endpoints de clientes."""

    def test_listar_clientes_vazio(self, override_get_db):
        """Testa listagem sem clientes."""
        response = client.get("/clientes/")
        assert response.status_code == 200
        assert response.json() == []

    def test_criar_cliente(self, override_get_db, monkeypatch):
        """Testa criacao de cliente com telefone sanitizado."""
        envios = []

        def fake_whatsapp(nome, telefone):
            envios.append(("whatsapp", nome, telefone))

        monkeypatch.setattr("src.clientes.router.enviar_boas_vindas", fake_whatsapp)
        payload = {
            "nome": "Joao Gabriel",
            "telefone": "(61) 9856-12117",
            "email": "joaogabriel@gmail.com",
            "pontos_fidelidade": 1,
        }
        response = client.post("/clientes/", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["nome"] == "Joao Gabriel"
        assert data["telefone"] == "61985612117"
        assert data["email"] == "joaogabriel@gmail.com"
        assert data["pontos_fidelidade"] == 1
        assert "data_cadastro" in data
        assert ("whatsapp", "Joao Gabriel", "61985612117") in envios

    def test_listar_clientes_com_filtro(self, override_get_db, cliente_valido):
        """Testa listagem com filtro por telefone."""
        response = client.get(
            "/clientes/",
            params={"telefone": cliente_valido.telefone},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == cliente_valido.id

    def test_obter_cliente_por_id(self, override_get_db, cliente_valido):
        """Testa obtencao de cliente por ID."""
        response = client.get(f"/clientes/{cliente_valido.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == cliente_valido.id
        assert data["nome"] == "Maria Silva"

    def test_obter_cliente_inexistente(self, override_get_db):
        """Testa obtencao de cliente inexistente."""
        response = client.get("/clientes/9999")
        assert response.status_code == 404
        assert "Cliente nao encontrado" in response.json()["detail"]

    def test_atualizar_cliente(self, override_get_db, cliente_valido):
        """Testa atualizacao de cliente existente."""
        payload = {"nome": "Maria Atualizada"}
        response = client.patch(f"/clientes/{cliente_valido.id}", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["nome"] == "Maria Atualizada"

    def test_atualizar_cliente_inexistente(self, override_get_db):
        """Testa atualizacao de cliente inexistente."""
        payload = {"nome": "Nao existe"}
        response = client.patch("/clientes/9999", json=payload)
        assert response.status_code == 404

    def test_excluir_cliente_soft_delete(self, override_get_db, cliente_valido):
        """Testa exclusao logica de cliente."""
        response = client.delete(f"/clientes/{cliente_valido.id}")
        assert response.status_code == 204

        response = client.get(f"/clientes/{cliente_valido.id}")
        assert response.status_code == 404

        response = client.get("/clientes/")
        assert response.status_code == 200
        assert response.json() == []

    def test_excluir_cliente_inexistente(self, override_get_db):
        """Testa exclusao de cliente inexistente."""
        response = client.delete("/clientes/9999")
        assert response.status_code == 404

    def test_conflito_telefone(self, override_get_db, cliente_valido):
        """Testa conflito de telefone duplicado."""
        payload = {
            "nome": "Outro",
            "telefone": cliente_valido.telefone,
            "email": "outro@email.com",
            "pontos_fidelidade": 0,
        }
        response = client.post("/clientes/", json=payload)
        assert response.status_code == 409
        assert "Telefone ja cadastrado" in response.json()["detail"]

    def test_validacao_email(self, override_get_db):
        """Testa validacao de email invalido."""
        payload = {
            "nome": "Invalido",
            "telefone": "83999990002",
            "email": "email-invalido",
            "pontos_fidelidade": 0,
        }
        response = client.post("/clientes/", json=payload)
        assert response.status_code == 422
