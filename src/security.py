import json
from time import monotonic
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from src.config import settings
from src.database import SessionLocal
from src.usuarios.model import Usuario

bearer_scheme = HTTPBearer(auto_error=False)

_jwks_cache: dict[str, Any] = {"keys": None, "expires_at": 0.0}

# Cache JWKS por 1 hora
_JWKS_CACHE_SECONDS = 3600


def _auth_exception(detail: str = "Credenciais invalidas") -> HTTPException:
    """Cria uma resposta 401 padronizada para falhas de autenticacao Bearer."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _fetch_jwks() -> dict[str, Any]:
    """Busca e guarda em cache as chaves publicas JWKS do Supabase Auth."""
    now = monotonic()
    cached_keys = _jwks_cache["keys"]
    if cached_keys and now < _jwks_cache["expires_at"]:
        return cached_keys

    jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    try:
        with urlopen(jwks_url, timeout=5) as response:
            jwks_raw = response.read().decode("utf-8")
    except (TimeoutError, URLError) as exc:
        raise _auth_exception(
            "Nao foi possivel consultar as chaves do Supabase Auth"
        ) from exc

    try:
        keys = json.loads(jwks_raw)
    except json.JSONDecodeError as exc:
        raise _auth_exception("Resposta invalida das chaves do Supabase Auth") from exc

    _jwks_cache["keys"] = keys
    _jwks_cache["expires_at"] = now + _JWKS_CACHE_SECONDS
    return keys


def _get_signing_key(token: str) -> dict[str, Any]:
    """Seleciona no JWKS a chave publica usada para assinar o token recebido."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise _auth_exception("Token invalido") from exc

    token_kid = header.get("kid")
    if not token_kid:
        raise _auth_exception("Token sem identificador de chave")

    for key in _fetch_jwks().get("keys", []):
        if key.get("kid") == token_kid:
            return key

    raise _auth_exception("Chave de assinatura do token nao encontrada")


def decode_supabase_token(token: str) -> dict[str, Any]:
    """Valida o JWT do Supabase Auth e retorna o payload."""
    key = _get_signing_key(token)
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[key.get("alg", "ES256")],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise _auth_exception("Token invalido ou expirado") from exc

    return payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    """Dependencia FastAPI que exige token Bearer valido e retorna o usuario atual."""
    if credentials is None:
        raise _auth_exception("Token de autenticacao ausente")

    if credentials.scheme.lower() != "bearer":
        raise _auth_exception("Esquema de autenticacao invalido")

    return decode_supabase_token(credentials.credentials)


def require_roles(*required_roles: str):
    """Cria uma dependencia FastAPI que exige pelo menos uma das roles informadas."""

    def dependency(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        """Valida se o usuario autenticado possui alguma role exigida."""
        # Suporte para testes que injetam as roles diretamente no mock do get_current_user
        if "roles" in user:
            user_roles = set(user["roles"])
            if user_roles.intersection(required_roles):
                return user
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario sem permissao para acessar este recurso",
            )

        sub = user.get("sub")
        if not sub:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario sem permissao para acessar este recurso",
            )

        db = SessionLocal()
        try:
            usuario = db.query(Usuario).filter(Usuario.auth_provider_id == sub).first()
            if not usuario or usuario.funcao.value not in required_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Usuario sem permissao para acessar este recurso",
                )
        finally:
            db.close()

        user["roles"] = [usuario.funcao.value]
        return user

    return dependency
