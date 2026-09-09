"""Testes da resolucao de usuario e funcao usada por require_roles."""

# pylint: disable=redefined-outer-name

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.main import app  # noqa: F401  registra os modelos no metadata
from src.security import _funcao_do_token, buscar_usuario_por_claims
from src.usuarios.model import FuncaoUsuario, Usuario

TEST_DATABASE_URL = "sqlite+pysqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def db_session():
    """Cria uma sessao SQLite isolada para os testes de seguranca."""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


def test_busca_usuario_pelo_auth_provider_id(db_session):
    """Garante que o vinculo com o provedor de autenticacao continua sendo a primeira busca."""
    usuario = Usuario(
        nome="Admin",
        email="admin@example.com",
        funcao=FuncaoUsuario.administrador,
        auth_provider_id="supabase-sub",
    )
    db_session.add(usuario)
    db_session.commit()

    encontrado = buscar_usuario_por_claims(
        db_session,
        {"sub": "supabase-sub", "email": "outro@example.com"},
    )
    assert encontrado is not None
    assert encontrado.email == "admin@example.com"


def test_busca_usuario_pelo_email_quando_auth_provider_id_nao_bate(db_session):
    """Garante o mesmo criterio do front: se o ID nao bate, tenta o e-mail."""
    usuario = Usuario(
        nome="Admin",
        email="admin@example.com",
        funcao=FuncaoUsuario.administrador,
        auth_provider_id=None,
    )
    db_session.add(usuario)
    db_session.commit()

    encontrado = buscar_usuario_por_claims(
        db_session,
        {"sub": "uuid-novo-do-supabase", "email": "admin@example.com"},
    )
    assert encontrado is not None
    assert encontrado.funcao == FuncaoUsuario.administrador


def test_nao_encontra_usuario_sem_id_nem_email(db_session):
    """Garante que claims incompletas nao resolvem um usuario."""
    assert buscar_usuario_por_claims(db_session, {"sub": None}) is None


def test_funcao_do_token_usa_user_metadata_e_ignora_role_authenticated():
    """Garante que o role padrao do Supabase nao vira permissao da aplicacao."""
    assert _funcao_do_token({"role": "authenticated"}) is None
    assert _funcao_do_token({"user_metadata": {"funcao": "administrador"}}) == "administrador"
    assert _funcao_do_token({"app_metadata": {"role": "caixa"}}) == "caixa"
