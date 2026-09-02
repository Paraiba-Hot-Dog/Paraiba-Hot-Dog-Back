"""Modulo de integracao com o Supabase Auth REST API.

Utiliza a API GoTrue do Supabase para login, signup, update e delete de usuarios.
"""

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import HTTPException, status

from src.config import settings


def _supabase_auth_url(path: str) -> str:
    """Constroi a URL completa para um endpoint do Supabase Auth."""
    base = settings.supabase_url.rstrip("/")
    return f"{base}/auth/v1/{path.lstrip('/')}"


def _request(
    method: str,
    url: str,
    *,
    data: dict[str, Any] | None = None,
    use_service_role: bool = False,
) -> tuple[int, Any]:
    """Executa uma requisicao HTTP ao Supabase Auth e retorna (status, body)."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "apikey": settings.supabase_service_role_key,
    }

    if use_service_role:
        headers["Authorization"] = f"Bearer {settings.supabase_service_role_key}"

    body = json.dumps(data).encode("utf-8") if data else None
    request = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8")
            parsed = json.loads(response_body) if response_body else None
            return response.status, parsed
    except HTTPError as erro:
        response_body = erro.read().decode("utf-8")
        try:
            conteudo = json.loads(response_body) if response_body else {}
        except json.JSONDecodeError:
            conteudo = {"message": response_body}
        return erro.code, conteudo
    except (TimeoutError, URLError) as erro:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Nao foi possivel conectar ao Supabase Auth",
        ) from erro


def login(email: str, password: str) -> dict[str, Any]:
    """Autentica um usuario via Supabase Auth e retorna os tokens."""
    status_code, body = _request(
        "POST",
        _supabase_auth_url("token?grant_type=password"),
        data={"email": email, "password": password},
    )

    if status_code != 200:
        msg = body.get("error_description") or body.get("msg") or "Credenciais invalidas"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=msg,
        )

    return body


def signup(email: str, password: str, user_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Cria um novo usuario no Supabase Auth e retorna seus dados."""
    payload: dict[str, Any] = {
        "email": email,
        "password": password,
        "email_confirm": True,
    }
    if user_metadata:
        payload["user_metadata"] = user_metadata

    status_code, body = _request(
        "POST",
        _supabase_auth_url("admin/users"),
        data=payload,
        use_service_role=True,
    )

    if status_code not in (200, 201):
        msg = body.get("msg") or body.get("message") or "Erro ao criar usuario"
        if "already" in msg.lower() or status_code == 422:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email ja cadastrado no auth")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=msg)

    return body


def update_user(user_id: str, *, email: str | None = None, password: str | None = None) -> None:
    """Atualiza email e/ou senha de um usuario no Supabase Auth."""
    if not user_id:
        return

    payload: dict[str, Any] = {}
    if email is not None:
        payload["email"] = email
    if password is not None:
        payload["password"] = password

    if not payload:
        return

    status_code, body = _request(
        "PUT",
        _supabase_auth_url(f"admin/users/{user_id}"),
        data=payload,
        use_service_role=True,
    )

    if status_code not in (200, 204):
        msg = body.get("msg") or body.get("message") or "Erro ao atualizar usuario"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=msg)


def delete_user(user_id: str | None) -> None:
    """Remove um usuario do Supabase Auth pelo ID."""
    if not user_id:
        return

    status_code, body = _request(
        "DELETE",
        _supabase_auth_url(f"admin/users/{user_id}"),
        use_service_role=True,
    )

    if status_code not in (200, 204, 404):
        msg = body.get("msg") or body.get("message") or "Erro ao remover usuario"
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=msg)
