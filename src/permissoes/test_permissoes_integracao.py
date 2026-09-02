"""Testes de integracao para os endpoints de permissoes."""

import os

import httpx
import pytest

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")

pytestmark = pytest.mark.integration


def _auth_headers() -> dict[str, str]:
    """Retorna headers de autenticacao ou pula o teste sem token."""
    if not API_AUTH_TOKEN:
        pytest.skip("Defina API_AUTH_TOKEN para rodar os testes de integracao.")
    return {"Authorization": f"Bearer {API_AUTH_TOKEN}"}


@pytest.fixture(name="api_client")
def fixture_api_client() -> httpx.Client:
    """Cria um cliente HTTP autenticado para os testes de permissoes."""
    with httpx.Client(timeout=10.0, headers=_auth_headers()) as client:
        try:
            health = client.get(f"{BASE_URL}/")
            health.raise_for_status()
        except httpx.HTTPError as exc:
            pytest.skip(f"API de integracao indisponivel em {BASE_URL}: {exc}")
        yield client


def test_atualizar_permissao_retorna_200(api_client: httpx.Client) -> None:
    """Garante que uma permissao existente pode ser atualizada."""
    list_response = api_client.get(f"{BASE_URL}/permissoes/")
    assert list_response.status_code == 200, list_response.text
    permissao = list_response.json()[0]

    patch_response = api_client.patch(
        f"{BASE_URL}/permissoes/{permissao['id']}",
        json={"nome": permissao["nome"]},
    )

    assert patch_response.status_code == 200, patch_response.text
    assert patch_response.json()["id"] == permissao["id"]
    assert patch_response.json()["nome"] == permissao["nome"]
