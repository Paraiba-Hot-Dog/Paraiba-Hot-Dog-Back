"""Testes de integracao local dos endpoints institucionais com TestClient."""

# Pylint doesn't understand pytest fixtures in this module.
# pylint: disable=redefined-outer-name,unused-argument

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.institucional.model import SobreNos
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

ESTATISTICAS_PADRAO = [
    {"valor": "10+", "legenda": "Anos de funcionamento"},
    {"valor": "4,9", "legenda": "Avaliação média"},
    {"valor": "3", "legenda": "Unidades"},
]


@pytest.fixture(scope="function")
def db_session():
    """Cria uma sessao SQLite isolada para cada teste institucional."""
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
def authenticated_admin():
    """Simula um usuario administrador autenticado para rotas protegidas."""
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-admin",
        "roles": ["administrador"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def authenticated_non_admin():
    """Simula um usuario autenticado sem a role administrador."""
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "test-user",
        "roles": ["caixa"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def texto_sobre_nos(db_session):
    """Cria o registro unico de Sobre Nos usado pela API."""
    conteudo = SobreNos(
        id=1,
        texto="Texto original de Sobre Nos.",
        estatisticas=ESTATISTICAS_PADRAO,
    )
    db_session.add(conteudo)
    db_session.commit()
    db_session.refresh(conteudo)
    return conteudo


def test_obter_sobre_nos_publico(override_get_db, texto_sobre_nos):
    """Garante que a leitura do texto e dos cards e publica e nao exige autenticacao."""
    response = client.get("/institucional/sobre-nos")
    assert response.status_code == 200
    corpo = response.json()
    assert corpo["texto"] == texto_sobre_nos.texto
    assert corpo["estatisticas"] == ESTATISTICAS_PADRAO


def test_atualizar_texto_sem_role_administrador_retorna_403(
    override_get_db, authenticated_non_admin, texto_sobre_nos
):
    """Garante que apenas administradores podem alterar o texto."""
    response = client.put(
        "/institucional/sobre-nos",
        json={
            "texto": "Tentativa de alteracao sem permissao.",
            "estatisticas": ESTATISTICAS_PADRAO,
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Usuario sem permissao para acessar este recurso"


def test_atualizar_texto_como_administrador(override_get_db, authenticated_admin, texto_sobre_nos):
    """Garante que um administrador consegue atualizar o texto de Sobre Nos."""
    novo_texto = "Texto atualizado pelo administrador."
    response = client.put(
        "/institucional/sobre-nos",
        json={"texto": novo_texto, "estatisticas": ESTATISTICAS_PADRAO},
    )
    assert response.status_code == 200
    assert response.json()["texto"] == novo_texto


def test_atualizar_estatisticas_como_administrador(
    override_get_db, authenticated_admin, texto_sobre_nos
):
    """Garante que um administrador consegue atualizar os cards de estatisticas."""
    novas_estatisticas = [
        {"valor": "12+", "legenda": "Anos de história"},
        {"valor": "5,0", "legenda": "Nota dos clientes"},
        {"valor": "4", "legenda": "Lojas"},
    ]
    response = client.put(
        "/institucional/sobre-nos",
        json={"texto": texto_sobre_nos.texto, "estatisticas": novas_estatisticas},
    )
    assert response.status_code == 200
    assert response.json()["estatisticas"] == novas_estatisticas


def test_atualizar_estatisticas_com_quantidade_invalida_retorna_422(
    override_get_db, authenticated_admin, texto_sobre_nos
):
    """Garante que os cards de estatisticas precisam ser exatamente tres."""
    response = client.put(
        "/institucional/sobre-nos",
        json={
            "texto": texto_sobre_nos.texto,
            "estatisticas": [{"valor": "1", "legenda": "Unidade"}],
        },
    )
    assert response.status_code == 422
