"""Testes do upload de imagens de produtos."""

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.produtos import router as produtos_router
from src.produtos.model import Categoria, Produto, Subcategoria


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
    """Cria uma sessao SQLite isolada para os testes de upload de produto."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        categoria = Categoria(nome="Hot Dogs")
        db.add(categoria)
        db.flush()
        subcategoria = Subcategoria(nome="Tradicionais", categoria_id=categoria.id)
        db.add(subcategoria)
        db.commit()
        yield db, subcategoria
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_criar_produto_relaciona_imagem(tmp_path, monkeypatch, db_session):
    """Garante criacao do produto ja relacionado com a imagem enviada."""
    db, subcategoria = db_session
    upload_dir = tmp_path / "uploads" / "produtos"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(produtos_router, "UPLOAD_DIR", upload_dir)
    arquivo = FakeUploadFile("produto.jpg", "image/jpeg", b"fake image content")

    request = FakeRequest(
        "multipart/form-data",
        {
            "nome": "Hot dog simples",
            "subcategoria_id": str(subcategoria.id),
            "descricao": "Classico",
            "ativo": "true",
            "pontos_fidelidade_por_unidade": "0",
            "disponivel_todas_unidades": "true",
            "imagem": arquivo,
        },
    )
    produto = asyncio.run(produtos_router.criar_produto(request, db))

    produto_salvo = db.get(Produto, produto.id)
    assert produto_salvo is not None
    assert produto_salvo.imagem_url == produto.imagem_url
    assert produto.imagem_url.startswith("/uploads/produtos/")
    assert produto.imagem_url.endswith(".jpg")
    assert len(list(upload_dir.iterdir())) == 1


def test_criar_produto_rejeita_arquivo_nao_imagem(tmp_path, monkeypatch, db_session):
    """Garante que produto aceita apenas arquivos de imagem."""
    db, _subcategoria = db_session
    upload_dir = tmp_path / "uploads" / "produtos"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(produtos_router, "UPLOAD_DIR", upload_dir)
    arquivo = FakeUploadFile("produto.txt", "text/plain", b"not an image")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(produtos_router.salvar_imagem_upload(arquivo))

    assert exc_info.value.status_code == 400
    assert db.query(Produto).count() == 0
    assert not list(upload_dir.iterdir())


def test_criar_produto_multipart_sem_imagem_retorna_422(tmp_path, monkeypatch, db_session):
    """Garante que multipart exige arquivo de imagem."""
    db, subcategoria = db_session
    upload_dir = tmp_path / "uploads" / "produtos"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(produtos_router, "UPLOAD_DIR", upload_dir)
    request = FakeRequest(
        "multipart/form-data",
        {
            "nome": "Hot dog simples",
            "subcategoria_id": str(subcategoria.id),
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(produtos_router.criar_produto(request, db))

    assert exc_info.value.status_code == 422
    assert db.query(Produto).count() == 0
    assert not list(upload_dir.iterdir())


def test_criar_produto_multipart_invalido_nao_salva_imagem(tmp_path, monkeypatch, db_session):
    """Garante que validacao acontece antes de gravar arquivo."""
    db, _subcategoria = db_session
    upload_dir = tmp_path / "uploads" / "produtos"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(produtos_router, "UPLOAD_DIR", upload_dir)
    request = FakeRequest(
        "multipart/form-data",
        {
            "nome": "Hot dog simples",
            "subcategoria_id": "abc",
            "imagem": FakeUploadFile("produto.jpg", "image/jpeg", b"fake image content"),
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(produtos_router.criar_produto(request, db))

    assert exc_info.value.status_code == 422
    assert db.query(Produto).count() == 0
    assert not list(upload_dir.iterdir())


def test_criar_produto_remove_imagem_quando_repository_falha(tmp_path, monkeypatch, db_session):
    """Garante limpeza do arquivo quando o banco falha depois do upload."""
    db, subcategoria = db_session
    upload_dir = tmp_path / "uploads" / "produtos"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(produtos_router, "UPLOAD_DIR", upload_dir)
    request = FakeRequest(
        "multipart/form-data",
        {
            "nome": "Hot dog simples",
            "subcategoria_id": str(subcategoria.id),
            "imagem": FakeUploadFile("produto.jpg", "image/jpeg", b"fake image content"),
        },
    )

    def _falha_repository(_db, _data):
        raise RuntimeError("falha no banco")

    monkeypatch.setattr(produtos_router.repository, "criar_produto", _falha_repository)

    with pytest.raises(RuntimeError):
        asyncio.run(produtos_router.criar_produto(request, db))

    assert not list(upload_dir.iterdir())


def test_atualizar_produto_multipart_troca_imagem(tmp_path, monkeypatch, db_session):
    """Garante que edicao multipart persiste a nova imagem e remove a antiga."""
    db, subcategoria = db_session
    upload_dir = tmp_path / "uploads" / "produtos"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(produtos_router, "UPLOAD_DIR", upload_dir)
    imagem_antiga = upload_dir / "antiga.jpg"
    imagem_antiga.write_bytes(b"old image")
    produto = Produto(
        nome="Hot dog simples",
        descricao="Classico",
        imagem_url="/uploads/produtos/antiga.jpg",
        subcategoria_id=subcategoria.id,
    )
    db.add(produto)
    db.commit()
    db.refresh(produto)
    request = FakeRequest(
        "multipart/form-data",
        {
            "nome": "Hot dog simples atualizado",
            "subcategoria_id": str(subcategoria.id),
            "descricao": "Classico",
            "ativo": "true",
            "pontos_fidelidade_por_unidade": "0",
            "disponivel_todas_unidades": "true",
            "imagem": FakeUploadFile("nova.jpg", "image/jpeg", b"new image"),
        },
    )

    atualizado = asyncio.run(produtos_router.atualizar_produto(produto.id, request, db))

    assert atualizado.imagem_url != "/uploads/produtos/antiga.jpg"
    assert atualizado.imagem_url.startswith("/uploads/produtos/")
    assert db.get(Produto, produto.id).imagem_url == atualizado.imagem_url
    assert not imagem_antiga.exists()
    assert len(list(upload_dir.iterdir())) == 1


def test_criar_produto_content_type_invalido_retorna_415(db_session):
    """Garante erro controlado para content type nao suportado."""
    db, _subcategoria = db_session
    request = FakeRequest("application/x-www-form-urlencoded")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(produtos_router.criar_produto(request, db))

    assert exc_info.value.status_code == 415
