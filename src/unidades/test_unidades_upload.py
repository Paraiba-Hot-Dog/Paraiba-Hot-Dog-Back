"""Testes do upload de imagens de unidades."""

import asyncio
from datetime import time

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.unidades import repository
from src.unidades import router as unidades_router
from src.unidades.model import Endereco, Unidade


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


class FakeMultipartRequest:
    def __init__(self, form_data: dict | None = None, content_type: str = "multipart/form-data"):
        self.headers = {"content-type": content_type}
        self._form_data = FakeForm(form_data or {})

    async def form(self):
        return self._form_data

    async def json(self):
        raise ValueError("json nao esperado")


@pytest.fixture(name="db_session")
def fixture_db_session():
    """Cria uma sessao SQLite isolada para os testes de upload de unidade."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_criar_unidade_relaciona_imagem(tmp_path, monkeypatch, db_session):
    """Garante criacao da unidade ja relacionada com a imagem enviada."""
    upload_dir = tmp_path / "uploads" / "unidades"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(unidades_router, "UPLOAD_DIR", upload_dir)
    arquivo = FakeUploadFile("unidade.png", "image/png", b"fake image content")

    request = FakeMultipartRequest(
        {
            "nome": "Unidade Centro",
            "abertura": "09:00:00",
            "fechamento": "22:00:00",
            "cep": "58000000",
            "logradouro": "Rua Principal",
            "bairro": "Centro",
            "cidade": "Joao Pessoa",
            "estado": "PB",
            "numero": "100",
            "complemento": None,
            "descricao": "Unidade principal",
            "imagem": arquivo,
        }
    )
    unidade = asyncio.run(unidades_router.criar_unidade(request, db_session))

    unidade_salva = db_session.get(Unidade, unidade.id)
    assert unidade_salva is not None
    assert unidade_salva.imagem == unidade.imagem
    assert unidade.imagem.startswith("/uploads/unidades/")
    assert unidade.imagem.endswith(".png")
    assert len(list(upload_dir.iterdir())) == 1


def test_criar_unidade_rejeita_arquivo_nao_imagem(tmp_path, monkeypatch, db_session):
    """Garante que unidade aceita apenas arquivos de imagem."""
    upload_dir = tmp_path / "uploads" / "unidades"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(unidades_router, "UPLOAD_DIR", upload_dir)
    arquivo = FakeUploadFile("unidade.txt", "text/plain", b"not an image")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(unidades_router.salvar_imagem_upload(arquivo))

    assert exc_info.value.status_code == 400
    assert db_session.query(Unidade).count() == 0
    assert not list(upload_dir.iterdir())


def test_unidade_multipart_valida_limite_estado(tmp_path, monkeypatch):
    """Garante 422 antes do banco quando estado excede o limite da coluna."""
    upload_dir = tmp_path / "uploads" / "unidades"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(unidades_router, "UPLOAD_DIR", upload_dir)
    request = FakeMultipartRequest(
        {
            "nome": "Unidade Centro",
            "abertura": "11:00:00",
            "fechamento": "23:00:00",
            "cep": "58000000",
            "logradouro": "Rua Principal",
            "numero": "100",
            "complemento": None,
            "bairro": "Centro",
            "cidade": "Joao Pessoa",
            "estado": "aoba",
            "descricao": "Unidade principal",
            "imagem": FakeUploadFile("unidade.png", "image/png", b"fake image content"),
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(unidades_router._unidade_data_from_request(request))

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail[0]["loc"] == ("estado",)
    assert not list(upload_dir.iterdir())


def test_criar_unidade_multipart_sem_imagem_retorna_422(tmp_path, monkeypatch, db_session):
    """Garante que multipart exige arquivo de imagem."""
    upload_dir = tmp_path / "uploads" / "unidades"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(unidades_router, "UPLOAD_DIR", upload_dir)
    request = FakeMultipartRequest(
        {
            "nome": "Unidade Centro",
            "abertura": "11:00:00",
            "fechamento": "23:00:00",
            "cep": "58000000",
            "logradouro": "Rua Principal",
            "bairro": "Centro",
            "cidade": "Joao Pessoa",
            "estado": "PB",
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(unidades_router.criar_unidade(request, db_session))

    assert exc_info.value.status_code == 422
    assert db_session.query(Unidade).count() == 0
    assert not list(upload_dir.iterdir())


def test_criar_unidade_remove_imagem_quando_repository_falha(tmp_path, monkeypatch, db_session):
    """Garante limpeza do arquivo quando o banco falha depois do upload."""
    upload_dir = tmp_path / "uploads" / "unidades"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(unidades_router, "UPLOAD_DIR", upload_dir)
    request = FakeMultipartRequest(
        {
            "nome": "Unidade Centro",
            "abertura": "11:00:00",
            "fechamento": "23:00:00",
            "cep": "58000000",
            "logradouro": "Rua Principal",
            "bairro": "Centro",
            "cidade": "Joao Pessoa",
            "estado": "PB",
            "imagem": FakeUploadFile("unidade.png", "image/png", b"fake image content"),
        }
    )

    def _falha_repository(_db, _data):
        raise RuntimeError("falha no banco")

    monkeypatch.setattr(unidades_router.repository, "criar_unidade", _falha_repository)

    with pytest.raises(RuntimeError):
        asyncio.run(unidades_router.criar_unidade(request, db_session))

    assert not list(upload_dir.iterdir())


def test_criar_unidade_content_type_invalido_retorna_415(db_session):
    """Garante erro controlado para content type nao suportado."""
    request = FakeMultipartRequest(content_type="application/x-www-form-urlencoded")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(unidades_router.criar_unidade(request, db_session))

    assert exc_info.value.status_code == 415


def _criar_unidade_no_banco(db_session, imagem: str | None = None) -> Unidade:
    """Auxiliar: cria endereco + unidade no banco e retorna a unidade."""
    endereco = Endereco(
        cep="58000000",
        logradouro="Rua Principal",
        bairro="Centro",
        cidade="Joao Pessoa",
        estado="PB",
    )
    db_session.add(endereco)
    db_session.flush()
    unidade = Unidade(
        nome="Unidade Teste",
        imagem=imagem,
        abertura=time(9, 0),
        fechamento=time(22, 0),
        endereco_id=endereco.id,
    )
    db_session.add(unidade)
    db_session.commit()
    db_session.refresh(unidade)
    return unidade


def test_atualizar_unidade_com_nova_imagem_troca_arquivo(tmp_path, monkeypatch, db_session):
    """Garante que ao enviar nova imagem no PATCH, o arquivo antigo e excluido."""
    upload_dir = tmp_path / "uploads" / "unidades"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(unidades_router, "UPLOAD_DIR", upload_dir)

    imagem_antiga_path = upload_dir / "old.png"
    imagem_antiga_path.write_bytes(b"conteudo antigo")
    unidade = _criar_unidade_no_banco(db_session, imagem="/uploads/unidades/old.png")

    nova_imagem = FakeUploadFile("new.jpg", "image/jpeg", b"conteudo novo")
    request = FakeMultipartRequest({"imagem": nova_imagem})

    asyncio.run(unidades_router.atualizar_unidade(request, unidade.id, db_session))

    assert not imagem_antiga_path.exists(), "imagem antiga deve ser excluida"
    db_session.refresh(unidade)
    assert unidade.imagem is not None
    assert unidade.imagem != "/uploads/unidades/old.png"
    assert unidade.imagem.endswith(".jpg")
    assert len(list(upload_dir.iterdir())) == 1


def test_atualizar_unidade_sem_nova_imagem_mantem_arquivo(tmp_path, monkeypatch, db_session):
    """Garante que ao nao enviar imagem no PATCH, o arquivo existente e preservado."""
    upload_dir = tmp_path / "uploads" / "unidades"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(unidades_router, "UPLOAD_DIR", upload_dir)

    imagem_path = upload_dir / "existing.png"
    imagem_path.write_bytes(b"imagem existente")
    unidade = _criar_unidade_no_banco(db_session, imagem="/uploads/unidades/existing.png")

    request = FakeMultipartRequest({"nome": "Nome Atualizado"})

    asyncio.run(unidades_router.atualizar_unidade(request, unidade.id, db_session))

    assert imagem_path.exists(), "imagem existente deve ser preservada"
    db_session.refresh(unidade)
    assert unidade.nome == "Nome Atualizado"
    assert unidade.imagem == "/uploads/unidades/existing.png"


def test_excluir_unidade_remove_imagem_e_endereco(tmp_path, monkeypatch, db_session):
    """Garante que ao excluir unidade, o arquivo de imagem e o endereco sao removidos."""
    upload_dir = tmp_path / "uploads" / "unidades"
    upload_dir.mkdir(parents=True)
    monkeypatch.setattr(unidades_router, "UPLOAD_DIR", upload_dir)

    imagem_path = upload_dir / "to_delete.png"
    imagem_path.write_bytes(b"imagem da unidade")
    unidade = _criar_unidade_no_banco(db_session, imagem="/uploads/unidades/to_delete.png")
    unidade_id = unidade.id
    endereco_id = unidade.endereco_id

    imagem_url = repository.excluir_unidade(db_session, unidade_id)
    unidades_router._remover_imagem_url(imagem_url)

    assert not imagem_path.exists(), "arquivo de imagem deve ser excluido"
    assert db_session.get(Unidade, unidade_id) is None, "unidade deve ser removida do banco"
    assert db_session.get(Endereco, endereco_id) is None, "endereco orfao deve ser removido do banco"
