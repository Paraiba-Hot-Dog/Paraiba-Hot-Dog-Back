"""Testes de integracao para os endpoints de clientes."""

# pylint: disable=redefined-outer-name

import os
from datetime import UTC, datetime

import httpx
import pytest

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")

pytestmark = pytest.mark.integration


def _payload_cliente(**overrides):
    """Monta um payload unico de cliente para testes de integracao."""
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    telefone = f"839{stamp[-8:]}"
    payload = {
        "nome": f"Cliente Integracao {stamp}",
        "telefone": telefone,
        "email": f"cliente{stamp}@email.com",
        "pontos_fidelidade": 0,
    }
    payload.update(overrides)
    return payload


def _auth_headers() -> dict[str, str]:
    """Retorna headers de autenticacao ou pula o teste sem token."""
    if not API_AUTH_TOKEN:
        pytest.skip("Defina API_AUTH_TOKEN para rodar os testes de integracao.")
    return {"Authorization": f"Bearer {API_AUTH_TOKEN}"}


@pytest.fixture(name="api_client")
def fixture_api_client() -> httpx.Client:
    """Cria um cliente HTTP autenticado para os testes de integracao."""
    with httpx.Client(timeout=10.0, headers=_auth_headers()) as client:
        try:
            health = client.get(f"{BASE_URL}/")
            health.raise_for_status()
        except httpx.HTTPError as exc:
            pytest.skip(f"API de integracao indisponivel em {BASE_URL}: {exc}")
        yield client


@pytest.fixture(name="cleanup_ids")
def fixture_cleanup_ids():
    """Remove clientes criados durante o teste ao final da execucao."""
    tracked = []
    yield tracked
    if not API_AUTH_TOKEN:
        return
    with httpx.Client(timeout=10.0, headers=_auth_headers()) as client:
        for cliente_id in reversed(tracked):
            client.delete(f"{BASE_URL}/clientes/{cliente_id}")


def test_criar_e_obter_cliente(api_client: httpx.Client, cleanup_ids) -> None:
    """Garante criacao e busca de cliente pela API real."""
    payload = _payload_cliente()

    create_response = api_client.post(f"{BASE_URL}/clientes/", json=payload)
    assert create_response.status_code == 201, create_response.text
    cliente_id = create_response.json()["id"]
    cleanup_ids.append(cliente_id)

    get_response = api_client.get(f"{BASE_URL}/clientes/{cliente_id}")

    assert get_response.status_code == 200, get_response.text
    body = get_response.json()
    assert body["id"] == cliente_id
    assert body["nome"] == payload["nome"]
    assert body["telefone"] == payload["telefone"]


def test_listar_clientes_retorna_200(api_client: httpx.Client) -> None:
    """Garante que a listagem de clientes responde com sucesso."""
    response = api_client.get(f"{BASE_URL}/clientes/")

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_obter_cliente_inexistente_retorna_404(api_client: httpx.Client) -> None:
    """Garante 404 ao buscar cliente inexistente."""
    response = api_client.get(f"{BASE_URL}/clientes/999999999")

    assert response.status_code == 404, response.text
    assert "Cliente nao encontrado" in response.json()["detail"]


def test_atualizar_cliente_altera_nome(api_client: httpx.Client, cleanup_ids) -> None:
    """Garante atualizacao do nome de um cliente existente."""
    create_response = api_client.post(f"{BASE_URL}/clientes/", json=_payload_cliente())
    assert create_response.status_code == 201, create_response.text
    cliente_id = create_response.json()["id"]
    cleanup_ids.append(cliente_id)

    patch_response = api_client.patch(
        f"{BASE_URL}/clientes/{cliente_id}",
        json={"nome": "Cliente Integracao Atualizado"},
    )

    assert patch_response.status_code == 200, patch_response.text
    body = patch_response.json()
    assert body["nome"] == "Cliente Integracao Atualizado"


def test_deletar_cliente_remove_e_get_retorna_404(
    api_client: httpx.Client,
    cleanup_ids,
) -> None:
    """Garante remocao de cliente e 404 na busca posterior."""
    create_response = api_client.post(f"{BASE_URL}/clientes/", json=_payload_cliente())
    assert create_response.status_code == 201, create_response.text
    cliente_id = create_response.json()["id"]

    delete_response = api_client.delete(f"{BASE_URL}/clientes/{cliente_id}")
    if delete_response.status_code != 204:
        cleanup_ids.append(cliente_id)

    assert delete_response.status_code == 204, delete_response.text

    get_response = api_client.get(f"{BASE_URL}/clientes/{cliente_id}")
    assert get_response.status_code == 404, get_response.text
    assert "Cliente nao encontrado" in get_response.json()["detail"]
