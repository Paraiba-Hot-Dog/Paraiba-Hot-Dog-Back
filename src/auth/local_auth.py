"""Login local para desenvolvimento, sem depender do Supabase Auth.

Ativado com AUTH_LOCAL=true no .env: a senha e conferida na coluna `senha`
da tabela usuarios do banco local e o token e assinado com AUTH_LOCAL_JWT_SECRET.
Nenhuma chamada e feita ao Supabase enquanto esse modo estiver ativo.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import HTTPException, status
from jose import JWTError, jwt

from src.config import settings
from src.database import SessionLocal
from src.usuarios.model import Usuario

ALGORITMO = "HS256"
EXPIRACAO_SEGUNDOS = 8 * 60 * 60


def gerar_hash_senha(senha: str) -> str:
    """Gera o hash bcrypt de uma senha para gravar na coluna `senha`."""
    return bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _senha_confere(senha: str, hash_senha: str | None) -> bool:
    """Compara a senha informada com o hash bcrypt salvo no banco local."""
    if not hash_senha:
        return False
    try:
        return bcrypt.checkpw(senha.encode("utf-8"), hash_senha.encode("utf-8"))
    except ValueError:
        return False


def login(email: str, password: str) -> dict[str, Any]:
    """Autentica um usuario pelo banco local e retorna um token no formato do Supabase."""
    db = SessionLocal()
    try:
        usuario = db.query(Usuario).filter(Usuario.email == email).first()
    finally:
        db.close()

    if (
        not usuario
        or not usuario.auth_provider_id
        or not _senha_confere(password, usuario.senha)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais invalidas",
        )

    # O `sub` segue sendo o auth_provider_id, que e como require_roles encontra o usuario.
    expira_em = datetime.now(timezone.utc) + timedelta(seconds=EXPIRACAO_SEGUNDOS)
    payload = {
        "sub": usuario.auth_provider_id,
        "email": usuario.email,
        "role": "authenticated",
        "exp": expira_em,
    }

    return {
        "access_token": jwt.encode(payload, settings.auth_local_jwt_secret, algorithm=ALGORITMO),
        "token_type": "bearer",
        "expires_in": EXPIRACAO_SEGUNDOS,
    }


def decode_local_token(token: str) -> dict[str, Any]:
    """Valida um token emitido pelo login local e retorna o payload."""
    try:
        return jwt.decode(
            token,
            settings.auth_local_jwt_secret,
            algorithms=[ALGORITMO],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
