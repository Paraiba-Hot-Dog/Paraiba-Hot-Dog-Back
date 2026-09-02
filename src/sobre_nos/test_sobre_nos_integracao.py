"""Testes de integracao local dos endpoints de sobre-nos com TestClient."""

# Pylint doesn't understand pytest fixtures in this module.
# pylint: disable=redefined-outer-name,unused-argument

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base, get_db
from src.main import app
from src.security import get_current_user
from src.sobre_nos.model import SobreNosImagem

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
    """Cria uma sessao SQLite isolada para cada teste de sobre-nos."""
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
        "roles": ["cliente"],
    }
    yield
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def imagem_valida(db_session):
    """Cria uma imagem de carrossel valida para os cenarios de leitura e escrita."""
    imagem = SobreNosImagem(imagem_url="/uploads/sobre_nos/existente.jpg", ordem=0, posicao="center center")
    db_session.add(imagem)
    db_session.commit()
    db_session.refresh(imagem)
    return imagem


def test_listar_vazio(override_get_db):
    """Garante que a listagem vazia retorna lista vazia."""
    response = client.get("/sobre-nos/imagens")
    assert response.status_code == 200
    assert response.json() == []


def test_listar_com_dados_ordenado(override_get_db, db_session):
    """Garante que a listagem retorna as imagens ordenadas pelo campo ordem."""
    db_session.add_all(
        [
            SobreNosImagem(imagem_url="/uploads/sobre_nos/b.jpg", ordem=1),
            SobreNosImagem(imagem_url="/uploads/sobre_nos/a.jpg", ordem=0),
        ]
    )
    db_session.commit()

    response = client.get("/sobre-nos/imagens")
    assert response.status_code == 200
    items = response.json()
    assert [item["imagem_url"] for item in items] == [
        "/uploads/sobre_nos/a.jpg",
        "/uploads/sobre_nos/b.jpg",
    ]


def test_criar_imagem_sem_role_administrador_retorna_403(override_get_db, authenticated_non_admin):
    """Garante que apenas administradores podem criar imagem."""
    response = client.post(
        "/sobre-nos/imagens",
        files={"imagem": ("nova.jpg", b"conteudo", "image/jpeg")},
    )
    assert response.status_code == 403


def test_criar_imagem_como_administrador(tmp_path, monkeypatch, override_get_db, authenticated_admin):
    """Garante que um administrador consegue cadastrar uma nova imagem via upload."""
    from src.sobre_nos import router as sobre_nos_router

    upload_dir = tmp_path / "uploads" / "sobre_nos"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(sobre_nos_router, "UPLOAD_DIR", upload_dir)

    response = client.post(
        "/sobre-nos/imagens",
        files={"imagem": ("nova.jpg", b"conteudo da imagem", "image/jpeg")},
        data={"posicao": "center top"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["imagem_url"].startswith("/uploads/sobre_nos/")
    assert data["posicao"] == "center top"
    assert len(list(upload_dir.iterdir())) == 1


def test_criar_imagem_rejeita_arquivo_nao_imagem(tmp_path, monkeypatch, override_get_db, authenticated_admin):
    """Garante que apenas arquivos de imagem sao aceitos."""
    from src.sobre_nos import router as sobre_nos_router

    upload_dir = tmp_path / "uploads" / "sobre_nos"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(sobre_nos_router, "UPLOAD_DIR", upload_dir)

    response = client.post(
        "/sobre-nos/imagens",
        files={"imagem": ("nova.txt", b"nao e imagem", "text/plain")},
    )
    assert response.status_code == 400
    assert not list(upload_dir.iterdir())


def test_atualizar_ordem_como_administrador(override_get_db, authenticated_admin, imagem_valida):
    """Garante que um administrador consegue reordenar uma imagem."""
    response = client.patch(f"/sobre-nos/imagens/{imagem_valida.id}", json={"ordem": 5})
    assert response.status_code == 200
    assert response.json()["ordem"] == 5


def test_excluir_imagem_remove_registro_e_arquivo(tmp_path, monkeypatch, override_get_db, authenticated_admin, db_session):
    """Garante que excluir remove o registro do banco e o arquivo fisico."""
    from src.sobre_nos import router as sobre_nos_router

    upload_dir = tmp_path / "uploads" / "sobre_nos"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(sobre_nos_router, "UPLOAD_DIR", upload_dir)

    arquivo = upload_dir / "para-excluir.jpg"
    arquivo.write_bytes(b"conteudo")
    imagem = SobreNosImagem(imagem_url="/uploads/sobre_nos/para-excluir.jpg", ordem=0)
    db_session.add(imagem)
    db_session.commit()
    db_session.refresh(imagem)

    response = client.delete(f"/sobre-nos/imagens/{imagem.id}")
    assert response.status_code == 204
    assert not arquivo.exists()

    response = client.patch(f"/sobre-nos/imagens/{imagem.id}", json={"ordem": 1})
    assert response.status_code == 404
