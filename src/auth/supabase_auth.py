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
    bearer: str | None = None,
) -> tuple[int, Any]:
    """Executa uma requisicao HTTP ao Supabase Auth e retorna (status, body)."""
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "apikey": settings.supabase_service_role_key,
    }

    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    elif use_service_role:
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


def _erro_auth(body: Any) -> tuple[str, str]:
    """Extrai codigo e mensagem de uma resposta de erro do Supabase Auth."""
    if not isinstance(body, dict):
        return "", "Erro ao criar usuario"

    error_code = str(body.get("error_code") or "").lower()
    msg = body.get("msg") or body.get("message") or body.get("error_description") or "Erro ao criar usuario"
    return error_code, str(msg)


def _email_duplicado(error_code: str, msg: str) -> bool:
    """Indica se o Supabase recusou o cadastro porque o e-mail ja existe."""
    texto = f"{error_code} {msg}".lower()
    return error_code in {"email_exists", "user_already_exists"} or "already" in texto


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
        error_code, msg = _erro_auth(body)
        if _email_duplicado(error_code, msg):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email ja cadastrado no auth")
        if error_code == "weak_password" or "password" in msg.lower():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A senha nao atende aos requisitos. Use pelo menos 8 caracteres.",
            )
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


def enviar_email_recuperacao(email: str, redirect_to: str) -> dict:
    """Pede ao Supabase que envie o link de recuperacao para a caixa da pessoa."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return {"status": "skipped", "reason": "missing_supabase"}

    status_code, body = _enviar_recover(email, redirect_to)
    if status_code not in (200, 201) and _redirecionamento_recusado(body):
        status_code, body = _enviar_recover(email, None)

    if status_code in (200, 201):
        return {"status": "sent"}

    error_code, msg = _erro_auth(body)
    return {"status": "error", "reason": error_code or msg}


def atualizar_senha_com_sessao(access_token: str, nova_senha: str) -> None:
    """Grava a nova senha usando a sessao aberta pelo link do e-mail."""
    status_code, body = _request(
        "PUT",
        _supabase_auth_url("user"),
        data={"password": nova_senha},
        bearer=access_token,
    )
    if status_code in (200, 204):
        return

    error_code, msg = _erro_auth(body)
    if error_code == "weak_password" or "password" in msg.lower():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A senha nao atende aos requisitos. Use pelo menos 8 caracteres.",
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Token de recuperacao invalido ou expirado",
    )


def _enviar_recover(email: str, redirect_to: str | None) -> tuple[int, Any]:
    payload: dict[str, Any] = {"email": email}
    if redirect_to:
        payload["redirect_to"] = redirect_to
    return _request(
        "POST",
        _supabase_auth_url("recover"),
        data=payload,
        use_service_role=True,
    )


def _redirecionamento_recusado(body: Any) -> bool:
    _, msg = _erro_auth(body)
    texto = msg.lower()
    return "redirect" in texto


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
