from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.auth.model import RecuperacaoSenhaToken
from src.auth.repository import (
    _hash_token,
    redefinir_senha,
    solicitar_recuperacao_senha,
)
from src.database import Base
from src.usuarios.model import FuncaoUsuario, Usuario

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


@pytest.fixture(name="db_session")
def fixture_db_session():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def _usuario(db_session, email: str = "maria@example.com", auth_provider_id: str = "auth-1") -> Usuario:
    usuario = Usuario(
        nome="Maria",
        email=email,
        auth_provider_id=auth_provider_id,
        funcao=FuncaoUsuario.caixa,
    )
    db_session.add(usuario)
    db_session.commit()
    db_session.refresh(usuario)
    return usuario


def test_esqueci_senha_envia_email_com_token(db_session, monkeypatch):
    chamadas = []
    _usuario(db_session)

    def fake_enviar(email, link_recuperacao):
        chamadas.append((email, link_recuperacao))
        return {"status": "sent"}

    monkeypatch.setattr("src.auth.repository.enviar_recuperacao_senha", fake_enviar)

    resultado = solicitar_recuperacao_senha(db_session, "maria@example.com")

    assert resultado["email_status"] == "sent"
    assert chamadas[0][0] == "maria@example.com"
    assert chamadas[0][1] == "http://localhost:3000/recuperar-senha"
    assert db_session.query(RecuperacaoSenhaToken).count() == 1


def test_esqueci_senha_aceita_email_com_maiusculas(db_session, monkeypatch):
    chamadas = []
    _usuario(db_session)

    def fake_enviar(email, link_recuperacao):
        chamadas.append((email, link_recuperacao))
        return {"status": "sent"}

    monkeypatch.setattr("src.auth.repository.enviar_recuperacao_senha", fake_enviar)

    resultado = solicitar_recuperacao_senha(db_session, "  Maria@Example.com  ")

    assert resultado["email_status"] == "sent"
    assert chamadas[0][0] == "maria@example.com"


def test_esqueci_senha_retorna_erro_quando_email_nao_e_enviado(db_session, monkeypatch):
    _usuario(db_session)
    monkeypatch.setattr(
        "src.auth.repository.enviar_recuperacao_senha",
        lambda email, link: {"status": "skipped", "reason": "missing_smtp_credentials"},
    )

    resultado = solicitar_recuperacao_senha(db_session, "maria@example.com")

    assert resultado["email_status"] == "error"


def test_esqueci_senha_bloqueia_reenvio_enquanto_o_link_vale(db_session, monkeypatch):
    agora = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    monkeypatch.setattr("src.auth.repository._agora", lambda: agora)
    _usuario(db_session)
    monkeypatch.setattr(
        "src.auth.repository.enviar_recuperacao_senha",
        lambda email, link: {"status": "sent"},
    )

    solicitar_recuperacao_senha(db_session, "maria@example.com")
    resultado = solicitar_recuperacao_senha(db_session, "maria@example.com")

    assert resultado["email_status"] == "cooldown"
    assert resultado["aguardar_segundos"] == 1800
    assert resultado["link_valido_minutos"] == 30
    assert db_session.query(RecuperacaoSenhaToken).count() == 1


def test_esqueci_senha_bloqueia_terceiro_email_na_mesma_hora(db_session, monkeypatch):
    agora = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    monkeypatch.setattr("src.auth.repository._agora", lambda: agora)
    enviados = []
    monkeypatch.setattr(
        "src.auth.repository.enviar_recuperacao_senha",
        lambda email, link: enviados.append(email) or {"status": "sent"},
    )
    for indice, email in enumerate(("a@example.com", "b@example.com", "c@example.com")):
        _usuario(db_session, email, f"auth-{indice}")
        resultado = solicitar_recuperacao_senha(db_session, email)

    assert resultado["email_status"] == "limite"
    assert resultado["aguardar_segundos"] == 3600
    assert enviados == ["a@example.com", "b@example.com"]


def test_esqueci_senha_com_email_inexistente_nao_envia_email(db_session, monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        "src.auth.repository.enviar_recuperacao_senha",
        lambda email, link: chamadas.append((email, link)),
    )

    resultado = solicitar_recuperacao_senha(db_session, "ausente@example.com")

    assert resultado["email_status"] == "skipped"
    assert not chamadas
    assert db_session.query(RecuperacaoSenhaToken).count() == 0


def test_redefinir_senha_atualiza_supabase_e_invalida_token(db_session, monkeypatch):
    chamadas = []
    usuario = _usuario(db_session)
    token = "token-valido"
    db_session.add(
        RecuperacaoSenhaToken(
            usuario_id=usuario.id,
            token_hash=_hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        "src.auth.repository.supabase_update_user",
        lambda user_id, **data: chamadas.append((user_id, data)),
    )

    redefinir_senha(db_session, token, "nova-senha")

    token_db = db_session.query(RecuperacaoSenhaToken).first()
    assert token_db.used_at is not None
    assert chamadas == [("auth-1", {"password": "nova-senha"})]


def test_redefinir_senha_rejeita_usuario_sem_auth(db_session, monkeypatch):
    usuario = _usuario(db_session)
    usuario.auth_provider_id = None
    token = "token-sem-auth"
    db_session.add(
        RecuperacaoSenhaToken(
            usuario_id=usuario.id,
            token_hash=_hash_token(token),
            expires_at=datetime.now(UTC) + timedelta(minutes=30),
            created_at=datetime.now(UTC),
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        "src.auth.repository.supabase_update_user",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("nao deveria atualizar")),
    )

    with pytest.raises(HTTPException) as exc_info:
        redefinir_senha(db_session, token, "nova-senha")

    assert exc_info.value.status_code == 400
    token_db = db_session.query(RecuperacaoSenhaToken).first()
    assert token_db.used_at is None


def test_redefinir_senha_rejeita_token_invalido(db_session):
    with pytest.raises(HTTPException) as exc_info:
        redefinir_senha(db_session, "nao-existe", "nova-senha")

    assert exc_info.value.status_code == 400


def test_redefinir_senha_rejeita_token_expirado(db_session):
    usuario = _usuario(db_session)
    token = "token-expirado"
    db_session.add(
        RecuperacaoSenhaToken(
            usuario_id=usuario.id,
            token_hash=_hash_token(token),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
            created_at=datetime.now(UTC) - timedelta(minutes=31),
        )
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        redefinir_senha(db_session, token, "nova-senha")

    assert exc_info.value.status_code == 400
