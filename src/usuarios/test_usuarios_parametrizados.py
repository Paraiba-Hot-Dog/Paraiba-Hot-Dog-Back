import os
from datetime import UTC, datetime

import httpx
import pytest

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")
pytestmark = pytest.mark.integration


def _unique_email(prefix: str) -> str:
    """Gera um e-mail unico para testes de usuarios."""
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}.{stamp}@example.com"


def _auth_headers() -> dict[str, str]:
    """Retorna headers de autenticacao ou pula o teste sem token."""
    if not API_AUTH_TOKEN:
        pytest.skip("Defina API_AUTH_TOKEN para rodar os testes de integracao.")
    return {"Authorization": f"Bearer {API_AUTH_TOKEN}"}


def _create_unidade() -> int:
    """Cria uma unidade real para vincular usuarios de integracao."""
    payload = {
        "nome": f"Unidade Teste {datetime.now(UTC).strftime('%H%M%S%f')}",
        "imagem": None,
        "abertura": "11:00:00",
        "fechamento": "23:00:00",
        "descricao": "Unidade para teste de integracao",
        "endereco": {
            "cep": "58000000",
            "logradouro": "Rua de Teste",
            "numero": "123",
            "complemento": None,
            "bairro": "Centro",
            "cidade": "Joao Pessoa",
            "estado": "PB",
        },
    }
    with httpx.Client(timeout=10.0, headers=_auth_headers()) as client:
        resp = client.post(f"{BASE_URL}/unidades/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture(name="api_client")
def fixture_api_client() -> httpx.Client:
    """Cria um cliente HTTP autenticado para os testes de usuarios."""
    with httpx.Client(timeout=10.0, headers=_auth_headers()) as client:
        try:
            health = client.get(f"{BASE_URL}/")
            health.raise_for_status()
        except httpx.HTTPError as exc:
            pytest.skip(f"API de integracao indisponivel em {BASE_URL}: {exc}")
        yield client


@pytest.fixture(name="cleanup_ids")
def fixture_cleanup_ids():
    """Remove usuarios e unidades criados durante o teste."""
    tracked = {"usuarios": [], "unidades": []}
    yield tracked
    if not API_AUTH_TOKEN:
        return
    with httpx.Client(timeout=10.0, headers=_auth_headers()) as client:
        for usuario_id in reversed(tracked["usuarios"]):
            client.delete(f"{BASE_URL}/usuarios/{usuario_id}")
        for unidade_id in reversed(tracked["unidades"]):
            client.delete(f"{BASE_URL}/unidades/{unidade_id}")


@pytest.mark.parametrize(
    "nome,funcao",
    [
        ("Usuario Caixa", "caixa"),
        ("Usuario Cozinha", "cozinha"),
        ("Usuario Admin", "administrador"),
    ],
)
def test_criar_usuario_com_unidade_valida(
    nome: str,
    funcao: str,
    api_client: httpx.Client,
    cleanup_ids,
) -> None:
    """Garante criacao de usuarios para funcoes validas."""
    unidade_id = _create_unidade()
    cleanup_ids["unidades"].append(unidade_id)
    payload = {
        "nome": nome,
        "email": _unique_email("usuario.valido"),
        "senha": "12345678",
        "funcao": funcao,
        "unidade_id": unidade_id,
        "permissao_ids": [],
    }

    response = api_client.post(f"{BASE_URL}/usuarios/", json=payload)
    if response.status_code == 201:
        cleanup_ids["usuarios"].append(response.json()["id"])

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == payload["email"]
    assert body["nome"] == payload["nome"]
    assert body["funcao"] == payload["funcao"]
    assert body["unidade_id"] == unidade_id


@pytest.mark.parametrize("unidade_id_invalida", [999999, 123456789])
def test_criar_usuario_com_unidade_inexistente_retorna_404(unidade_id_invalida: int, api_client: httpx.Client) -> None:
    """Garante 404 ao criar usuario com unidade inexistente."""
    payload = {
        "nome": "Usuario Unidade Invalida",
        "email": _unique_email("usuario.invalido"),
        "senha": "12345678",
        "funcao": "caixa",
        "unidade_id": unidade_id_invalida,
        "permissao_ids": [],
    }

    response = api_client.post(f"{BASE_URL}/usuarios/", json=payload)

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Unidade nao encontrada"
