"""Testes parametrizados dos endpoints de blog."""

# Pylint doesn't understand pytest fixtures in this module.
# pylint: disable=redefined-outer-name,unused-argument

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.blog.model import Blog, TipoNoticiaPromocao
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
    """Cria uma sessao SQLite isolada para cada teste de blog."""
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
def post_valido(db_session):
    """Cria um post valido para os cenarios parametrizados."""
    post = Blog(
        titulo="Nova Unidade Abre",
        imagem_url="https://example.com/post.jpg",
        descricao="Abrimos uma nova unidade no Lago Sul",
        tipo=TipoNoticiaPromocao.noticia,
        data=date(2026, 4, 10),
    )
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)
    return post


@pytest.mark.parametrize("tipo", ["noticia", "promocao"])
def test_criar_post(override_get_db, authenticated_user, tipo):
    """Garante criacao de post para cada tipo permitido."""
    payload = {
        "titulo": f"Post {tipo}",
        "imagem_url": "https://example.com/promo.jpg",
        "descricao": "Aproveite nossa promoção",
        "tipo": tipo,
        "data": "2026-05-01",
    }
    response = client.post("/blog/", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["titulo"] == payload["titulo"]
    assert data["tipo"] == tipo


@pytest.mark.parametrize(
    "payload",
    [
        {"imagem_url": "https://example.com/x.jpg", "tipo": "noticia", "data": "2026-05-01"},
        {"titulo": "Sem Tipo", "imagem_url": "https://example.com/x.jpg", "data": "2026-05-01"},
    ],
)
def test_criar_invalido_retorna_422(override_get_db, authenticated_user, payload):
    """Garante erro de validacao para payloads invalidos."""
    response = client.post("/blog/", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("metodo", ["post", "patch", "delete"])
def test_rotas_protegidas_sem_token_retorna_401(override_get_db, unauthenticated_user, post_valido, metodo):
    """Garante 401 nas rotas protegidas sem usuario autenticado."""
    if metodo == "post":
        payload = {
            "titulo": "Promoção de Verão",
            "imagem_url": "https://example.com/promo.jpg",
            "descricao": "Aproveite nossa promoção",
            "tipo": "promocao",
            "data": "2026-05-01",
        }
        response = client.post("/blog/", json=payload)
    elif metodo == "patch":
        response = client.patch(f"/blog/{post_valido.id}", json={"titulo": "Novo título"})
    else:
        response = client.delete(f"/blog/{post_valido.id}")

    assert response.status_code == 401
