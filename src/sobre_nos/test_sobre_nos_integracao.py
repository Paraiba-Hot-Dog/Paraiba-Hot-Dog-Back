"""Testes de integracao dos endpoints de sobre-nos e compatibilidade institucional."""

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
from src.sobre_nos import router as sobre_nos_router
from src.sobre_nos.model import SobreNos, SobreNosImagem

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


@pytest.fixture
def imagem_valida(db_session):
    """Cria uma imagem de carrossel valida para os testes."""
    imagem = SobreNosImagem(
        imagem_url="/uploads/sobre_nos/existente.jpg",
        ordem=0,
        posicao="center center",
    )
    db_session.add(imagem)
    db_session.commit()
    db_session.refresh(imagem)
    return imagem


# ---------------------------------------------------------------------------
# Testes do Texto e Estatisticas (/sobre-nos e alias legado)
# ---------------------------------------------------------------------------


def test_obter_sobre_nos_publico(override_get_db, texto_sobre_nos):
    """Garante que a leitura do texto e dos cards e publica."""
    response = client.get("/sobre-nos")
    assert response.status_code == 200
    corpo = response.json()
    assert corpo["texto"] == texto_sobre_nos.texto
    assert corpo["estatisticas"] == ESTATISTICAS_PADRAO


def test_obter_sobre_nos_alias_legado(override_get_db, texto_sobre_nos):
    """Garante retrocompatibilidade com /institucional/sobre-nos."""
    response = client.get("/institucional/sobre-nos")
    assert response.status_code == 200
    corpo = response.json()
    assert corpo["texto"] == texto_sobre_nos.texto


def test_atualizar_texto_sem_role_administrador_retorna_403(
    override_get_db, authenticated_non_admin, texto_sobre_nos
):
    """Garante que apenas administradores podem alterar o texto."""
    response = client.put(
        "/sobre-nos",
        json={
            "texto": "Tentativa de alteracao sem permissao.",
            "estatisticas": ESTATISTICAS_PADRAO,
        },
    )
    assert response.status_code == 403


def test_atualizar_texto_como_administrador(
    override_get_db, authenticated_admin, texto_sobre_nos
):
    """Garante que um administrador consegue atualizar o texto de Sobre Nos."""
    novo_texto = "Texto atualizado pelo administrador com sucesso."
    response = client.put(
        "/sobre-nos",
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
        "/sobre-nos",
        json={"texto": texto_sobre_nos.texto, "estatisticas": novas_estatisticas},
    )
    assert response.status_code == 200
    assert response.json()["estatisticas"] == novas_estatisticas


def test_atualizar_estatisticas_com_quantidade_invalida_retorna_422(
    override_get_db, authenticated_admin, texto_sobre_nos
):
    """Garante que os cards de estatisticas precisam ser exatamente tres."""
    response = client.put(
        "/sobre-nos",
        json={
            "texto": texto_sobre_nos.texto,
            "estatisticas": [{"valor": "1", "legenda": "Unidade"}],
        },
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Testes do Carrossel de Imagens (/sobre-nos/imagens)
# ---------------------------------------------------------------------------


def test_listar_imagens_vazio(override_get_db):
    """Garante que a listagem vazia retorna lista vazia."""
    response = client.get("/sobre-nos/imagens")
    assert response.status_code == 200
    assert response.json() == []


def test_listar_imagens_com_dados_ordenado(override_get_db, db_session):
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


def test_criar_imagem_sem_role_administrador_retorna_403(
    override_get_db, authenticated_non_admin
):
    """Garante que apenas administradores podem enviar imagem."""
    response = client.post(
        "/sobre-nos/imagens",
        files={"imagem": ("nova.jpg", b"conteudo", "image/jpeg")},
    )
    assert response.status_code == 403


def test_criar_imagem_como_administrador(
    tmp_path, monkeypatch, override_get_db, authenticated_admin
):
    """Garante upload correto de imagem por administrador."""
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


def test_criar_imagem_rejeita_arquivo_invalido(
    tmp_path, monkeypatch, override_get_db, authenticated_admin
):
    """Garante que arquivos com tipo invalido sao rejeitados com 400."""
    upload_dir = tmp_path / "uploads" / "sobre_nos"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(sobre_nos_router, "UPLOAD_DIR", upload_dir)

    response = client.post(
        "/sobre-nos/imagens",
        files={"imagem": ("arquivo.txt", b"nao e imagem", "text/plain")},
    )
    assert response.status_code == 400


def test_criar_video_mp4_como_administrador(
    tmp_path, monkeypatch, override_get_db, authenticated_admin
):
    """Aceita MP4 pequeno e preserva extensao."""
    upload_dir = tmp_path / "uploads" / "sobre_nos"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(sobre_nos_router, "UPLOAD_DIR", upload_dir)

    response = client.post(
        "/sobre-nos/imagens",
        files={"imagem": ("historia.mp4", b"video pequeno", "video/mp4")},
    )
    assert response.status_code == 201
    assert response.json()["imagem_url"].endswith(".mp4")


def test_criar_video_rejeita_arquivo_acima_do_limite(
    tmp_path, monkeypatch, override_get_db, authenticated_admin
):
    """Rejeita video acima do limite com 413."""
    upload_dir = tmp_path / "uploads" / "sobre_nos"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(sobre_nos_router, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(sobre_nos_router, "LIMITE_VIDEO_BYTES", 10)

    response = client.post(
        "/sobre-nos/imagens",
        files={"imagem": ("grande.mp4", b"12345678901", "video/mp4")},
    )
    assert response.status_code == 413


def test_atualizar_ordem_imagem_como_administrador(
    override_get_db, authenticated_admin, imagem_valida
):
    """Garante atualizacao de ordem de uma imagem."""
    response = client.patch(
        f"/sobre-nos/imagens/{imagem_valida.id}", json={"ordem": 7}
    )
    assert response.status_code == 200
    assert response.json()["ordem"] == 7


def test_excluir_imagem_remove_registro_e_arquivo(
    tmp_path, monkeypatch, override_get_db, authenticated_admin, db_session
):
    """Garante que excluir imagem remove do banco e deleta o arquivo físico."""
    upload_dir = tmp_path / "uploads" / "sobre_nos"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(sobre_nos_router, "UPLOAD_DIR", upload_dir)

    arquivo = upload_dir / "foto-teste.jpg"
    arquivo.write_bytes(b"bytes")
    imagem = SobreNosImagem(imagem_url="/uploads/sobre_nos/foto-teste.jpg", ordem=0)
    db_session.add(imagem)
    db_session.commit()
    db_session.refresh(imagem)

    response = client.delete(f"/sobre-nos/imagens/{imagem.id}")
    assert response.status_code == 204
    assert not arquivo.exists()
