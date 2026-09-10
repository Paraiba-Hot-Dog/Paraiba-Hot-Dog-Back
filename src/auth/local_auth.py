"""Autenticacao opcional para desenvolvimento local, sem Supabase."""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from jose import JWTError, jwt
from passlib.hash import pbkdf2_sha256
from sqlalchemy.orm import Session

from src.config import settings
from src.usuarios.model import Usuario

ISSUER = "paraiba-local"
AUDIENCE = "paraiba-local-api"


def _secret() -> str:
    if not settings.local_auth_enabled or len(settings.local_auth_secret) < 32:
        raise HTTPException(503, "Autenticacao local nao configurada")
    return settings.local_auth_secret


def login(db: Session, email: str, password: str) -> dict:
    secret = _secret()
    usuario = db.query(Usuario).filter(Usuario.email == email).first()
    senha = usuario.senha if usuario else None
    if not senha or not pbkdf2_sha256.identify(senha) or not pbkdf2_sha256.verify(password, senha):
        raise HTTPException(401, "Credenciais invalidas")
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": usuario.auth_provider_id or f"local:{usuario.id}",
            "email": usuario.email,
            "user_metadata": {"funcao": usuario.funcao.value},
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "exp": now + timedelta(hours=8),
        },
        secret,
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": 28800}


def decode_token(token: str) -> dict:
    secret = _secret()
    try:
        return jwt.decode(
            token, secret, algorithms=["HS256"], audience=AUDIENCE, issuer=ISSUER,
            options={"require_exp": True, "require_sub": True},
        )
    except JWTError as exc:
        raise HTTPException(401, "Token invalido ou expirado") from exc
