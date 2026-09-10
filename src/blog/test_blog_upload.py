"""Testes do upload de imagens do blog."""

import asyncio
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.blog.model import Blog, TipoNoticiaPromocao
from src.blog import router as blog_router
from src.database import Base


class FakeUploadFile:
    def __init__(self, filename: str, content_type: str, content: bytes):
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self) -> bytes:
        return self._content


class FakeForm(dict):
    def getlist(self, key: str) -> list:
        value = self.get(key)
        return value if isinstance(value, list) else []


class FakeRequest:
    def __init__(self, content_type: str, form_data: dict | None = None):
        self.headers = {"content-type": content_type}
        self._form_data = FakeForm(form_data or {})

    async def form(self):
        return self._form_data

    async def json(self):
        raise ValueError("json nao esperado")


@pytest.fixture(name="db_session")
def fixture_db_session():
    """Cria uma sessao SQLite isolada para os testes de upload do blog."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine, tables=[Blog.__table__])
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine, tables=[Blog.__table__])


def test_criar_post_relaciona_imagem_ao_blog(tmp_path, monkeypatch, db_session):
    """Garante criacao do post ja relacionado com a imagem enviada."""
    upload_dir = tmp_path / "uploads" / "blog"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(blog_router, "UPLOAD_DIR", upload_dir)
    arquivo = FakeUploadFile("post.jpg", "image/jpeg", b"fake image content")

    request = FakeRequest(
        "multipart/form-data",
        {
            "titulo": "Promocao nova",
            "tipo": TipoNoticiaPromocao.promocao.value,
            "data": "2026-06-12",
            "descricao": "Descricao da promocao",
            "imagem": arquivo,
        },
    )
    post = asyncio.run(blog_router.criar_post(request, db_session))

    post_salvo = db_session.get(Blog, post.id)
    assert post_salvo is not None
    assert post_salvo.imagem_url == post.imagem_url
    assert post.imagem_url.startswith("/uploads/blog/")
    assert post.imagem_url.endswith(".jpg")
    assert len(list(upload_dir.iterdir())) == 1


def test_criar_post_rejeita_arquivo_nao_imagem(tmp_path, monkeypatch, db_session):
    """Garante que o endpoint aceita apenas arquivos de imagem."""
    upload_dir = tmp_path / "uploads" / "blog"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(blog_router, "UPLOAD_DIR", upload_dir)
    arquivo = FakeUploadFile("post.txt", "text/plain", b"not an image")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(blog_router.salvar_imagem_upload(arquivo))

    assert exc_info.value.status_code == 400
    assert db_session.query(Blog).count() == 0
    assert not list(upload_dir.iterdir())


def test_criar_post_multipart_sem_imagem_retorna_422(tmp_path, monkeypatch, db_session):
    """Garante que multipart exige arquivo de imagem."""
    upload_dir = tmp_path / "uploads" / "blog"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(blog_router, "UPLOAD_DIR", upload_dir)
    request = FakeRequest(
        "multipart/form-data",
        {
            "titulo": "Promocao nova",
            "tipo": TipoNoticiaPromocao.promocao.value,
            "data": "2026-06-12",
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(blog_router.criar_post(request, db_session))

    assert exc_info.value.status_code == 422
    assert db_session.query(Blog).count() == 0
    assert not list(upload_dir.iterdir())


def test_criar_post_multipart_invalido_nao_salva_imagem(tmp_path, monkeypatch, db_session):
    """Garante que validacao acontece antes de gravar arquivo."""
    upload_dir = tmp_path / "uploads" / "blog"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(blog_router, "UPLOAD_DIR", upload_dir)
    request = FakeRequest(
        "multipart/form-data",
        {
            "tipo": TipoNoticiaPromocao.promocao.value,
            "data": "2026-06-12",
            "imagem": FakeUploadFile("post.jpg", "image/jpeg", b"fake image content"),
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(blog_router.criar_post(request, db_session))

    assert exc_info.value.status_code == 422
    assert db_session.query(Blog).count() == 0
    assert not list(upload_dir.iterdir())


def test_criar_post_remove_imagem_quando_repository_falha(tmp_path, monkeypatch, db_session):
    """Garante limpeza do arquivo quando o banco falha depois do upload."""
    upload_dir = tmp_path / "uploads" / "blog"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(blog_router, "UPLOAD_DIR", upload_dir)
    request = FakeRequest(
        "multipart/form-data",
        {
            "titulo": "Promocao nova",
            "tipo": TipoNoticiaPromocao.promocao.value,
            "data": "2026-06-12",
            "imagem": FakeUploadFile("post.jpg", "image/jpeg", b"fake image content"),
        },
    )

    def _falha_repository(_db, _data):
        raise RuntimeError("falha no banco")

    monkeypatch.setattr(blog_router.repository, "criar_post", _falha_repository)

    with pytest.raises(RuntimeError):
        asyncio.run(blog_router.criar_post(request, db_session))

    assert not list(upload_dir.iterdir())


def test_criar_post_content_type_invalido_retorna_415(db_session):
    """Garante erro controlado para content type nao suportado."""
    request = FakeRequest("application/x-www-form-urlencoded")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(blog_router.criar_post(request, db_session))

    assert exc_info.value.status_code == 415
