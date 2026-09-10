import json
from time import monotonic
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from src.auth.local_auth import decode_token as decode_local_token
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
    if settings.local_auth_enabled:
        return decode_local_token(token)
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


_FUNCOES_VALIDAS = {"administrador", "caixa", "cozinha"}


def _sem_permissao() -> HTTPException:
    """Resposta 403 padronizada para falta de role na aplicacao."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Usuario sem permissao para acessar este recurso",
    )


def _email_do_token(user: dict[str, Any]) -> str | None:
    """Extrai um e-mail utilizavel do payload JWT, no mesmo criterio do front."""
    email = user.get("email") or user.get("preferred_username")
    if isinstance(email, str) and "@" in email:
        return email
    return None


def _funcao_do_token(user: dict[str, Any]) -> str | None:
    """Le a funcao da aplicacao no metadata do token, ignorando o role 'authenticated' do Supabase."""
    metadata = user.get("user_metadata")
    if isinstance(metadata, dict) and metadata.get("funcao") in _FUNCOES_VALIDAS:
        return metadata["funcao"]

    app_metadata = user.get("app_metadata")
    if isinstance(app_metadata, dict) and app_metadata.get("role") in _FUNCOES_VALIDAS:
        return app_metadata["role"]

    return None


def buscar_usuario_por_claims(db, user: dict[str, Any]) -> Usuario | None:
    """Localiza o usuario pelo ID do provedor de auth e, se faltar, pelo e-mail do token."""
    sub = user.get("sub")
    if sub:
        usuario = db.query(Usuario).filter(Usuario.auth_provider_id == sub).first()
        if usuario:
            return usuario

    email = _email_do_token(user)
    if email:
        return db.query(Usuario).filter(Usuario.email == email).first()

    return None


def require_roles(*required_roles: str):
    """Cria uma dependencia FastAPI que exige pelo menos uma das roles informadas."""

    def dependency(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        """Valida se o usuario autenticado possui alguma role exigida."""
        # Suporte para testes que injetam as roles diretamente no mock do get_current_user
        raw_roles = user.get("roles")
        if isinstance(raw_roles, (list, tuple, set)):
            if set(raw_roles).intersection(required_roles):
                return user
            raise _sem_permissao()

        db = SessionLocal()
        try:
            usuario = buscar_usuario_por_claims(db, user)
        finally:
            db.close()

        if usuario:
            if usuario.funcao.value not in required_roles:
                raise _sem_permissao()
            user["roles"] = [usuario.funcao.value]
            return user

        funcao_token = _funcao_do_token(user)
        if funcao_token in required_roles:
            user["roles"] = [funcao_token]
            return user

        raise _sem_permissao()

    return dependency
