"""Testes parametrizados para os endpoints de unidades."""

# pylint: disable=redefined-outer-name,unused-argument

from datetime import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app
from src.security import get_current_user
from src.unidades.model import Endereco, Unidade

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
def endereco_valido(db_session):
    """Cria um endereco valido para os testes."""
    endereco = Endereco(
        cep="58000000",
        logradouro="Rua Test",
        numero="123",
        complemento="Apto 1",
        bairro="Centro",
        cidade="Joao Pessoa",
        estado="PB",
    )
    db_session.add(endereco)
    db_session.commit()
    db_session.refresh(endereco)
    return endereco


@pytest.fixture
def unidade_valida(db_session, endereco_valido):
    """Cria uma unidade valida para os testes."""
    unidade = Unidade(
        nome="Unidade Centro",
        imagem="https://example.com/unidade.jpg",
        abertura=time(10, 0),
        fechamento=time(22, 0),
        descricao="Unidade principal",
        endereco_id=endereco_valido.id,
    )
    db_session.add(unidade)
    db_session.commit()
    db_session.refresh(unidade)
    return unidade


def _payload_unidade(**overrides):
    """Monta um payload base de unidade para os testes."""
    payload = {
        "nome": "Unidade Campina Grande",
        "imagem": "https://example.com/campina.jpg",
        "abertura": "11:00:00",
        "fechamento": "23:00:00",
        "descricao": "Unidade em Campina Grande",
        "endereco": {
            "cep": "58100000",
            "logradouro": "Av. Brasilia",
            "numero": "456",
            "complemento": "Loja 2",
            "bairro": "Prata",
            "cidade": "Campina Grande",
            "estado": "PB",
        },
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    "rota",
    [
        "/unidades/9999",
        "/unidades/123456",
    ],
)
def test_obter_unidade_inexistente_retorna_404(override_get_db, rota):
    """Garante 404 para rotas de unidades inexistentes."""
    response = client.get(rota)

    assert response.status_code == 404
    assert response.json()["detail"] == "Unidade nao encontrada"


@pytest.mark.parametrize(
    "payload,cidade_esperada",
    [
        (_payload_unidade(), "Campina Grande"),
        (
            _payload_unidade(
                nome="Unidade Joao Pessoa",
                imagem=None,
                descricao=None,
                endereco={
                    "cep": "58000000",
                    "logradouro": "Rua de Teste",
                    "numero": "123",
                    "complemento": None,
                    "bairro": "Centro",
                    "cidade": "Joao Pessoa",
                    "estado": "PB",
                },
            ),
            "Joao Pessoa",
        ),
    ],
)
def test_criar_unidade_com_payloads_validos(
    override_get_db,
    payload,
    cidade_esperada,
):
    """Garante criacao de unidade com payloads validos."""
    response = client.post("/unidades/", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["nome"] == payload["nome"]
    assert body["abertura"] == payload["abertura"]
    assert body["endereco"]["cidade"] == cidade_esperada


@pytest.mark.parametrize(
    "payload",
    [
        _payload_unidade(endereco={"cep": "58000000", "logradouro": "Rua Teste"}),
        _payload_unidade(endereco=None),
        _payload_unidade(abertura="25:00:00"),
        _payload_unidade(fechamento="99:00:00"),
        _payload_unidade(nome=None),
    ],
)
def test_criar_unidade_com_payloads_invalidos_retorna_422(
    override_get_db,
    payload,
):
    """Garante 422 para payloads invalidos de unidade."""
    response = client.post("/unidades/", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "rota",
    [
        "/unidades/9999",
        "/unidades/123456",
    ],
)
def test_excluir_unidade_inexistente_retorna_404(override_get_db, rota):
    """Garante 404 ao excluir unidade inexistente."""
    response = client.delete(rota)

    assert response.status_code == 404
    assert response.json()["detail"] == "Unidade nao encontrada"


def test_listar_unidades_vazio_retorna_lista_vazia(override_get_db):
    """Garante listagem vazia quando nao ha unidades."""
    response = client.get("/unidades/")

    assert response.status_code == 200
    assert response.json() == []


def test_listar_unidades_com_dados(override_get_db, unidade_valida):
    """Garante listagem de unidade cadastrada."""
    response = client.get("/unidades/")

    assert response.status_code == 200
    unidades = response.json()
    assert len(unidades) == 1
    assert unidades[0]["nome"] == unidade_valida.nome
    assert unidades[0]["abertura"] == "10:00:00"
    assert unidades[0]["fechamento"] == "22:00:00"


def test_obter_unidade_existente_retorna_endereco(override_get_db, unidade_valida):
    """Garante busca de unidade existente com endereco."""
    response = client.get(f"/unidades/{unidade_valida.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == unidade_valida.id
    assert body["nome"] == "Unidade Centro"
    assert body["descricao"] == "Unidade principal"
    assert body["endereco"]["cep"] == "58000000"
    assert body["endereco"]["logradouro"] == "Rua Test"
    assert body["endereco"]["numero"] == "123"
    assert body["endereco"]["bairro"] == "Centro"
    assert body["endereco"]["cidade"] == "Joao Pessoa"
    assert body["endereco"]["estado"] == "PB"


def test_excluir_unidade_existente_remove_registro(override_get_db, unidade_valida):
    """Garante exclusao de unidade existente."""
    unidade_id = unidade_valida.id

    delete_response = client.delete(f"/unidades/{unidade_id}")
    get_response = client.get(f"/unidades/{unidade_id}")

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


def test_criar_unidade_com_mapa_url(override_get_db):
    """Garante que mapa_url e salvo e retornado ao criar unidade."""
    payload = _payload_unidade()
    payload["mapa_url"] = "https://maps.example.com/unidade-campina"

    response = client.post("/unidades/", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["mapa_url"] == "https://maps.example.com/unidade-campina"


def test_criar_unidade_sem_mapa_url_retorna_none(override_get_db):
    """Garante que mapa_url e None quando nao informado."""
    response = client.post("/unidades/", json=_payload_unidade())

    assert response.status_code == 201
    assert response.json()["mapa_url"] is None


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/unidades/", {"json": _payload_unidade()}),
        ("patch", "/unidades/9999", {"json": {"nome": "Novo"}}),
        ("delete", "/unidades/9999", {}),
    ],
)
def test_operacao_restrita_sem_role_administrador_retorna_403(override_get_db, method, path, body):
    """Garante 403 para usuarios sem role administrador em operacoes de escrita."""
    app.dependency_overrides[get_current_user] = lambda: {"sub": "user", "roles": ["caixa"]}

    response = getattr(client, method)(path, **body)

    assert response.status_code == 403
