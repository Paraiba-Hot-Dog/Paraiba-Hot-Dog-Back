"""Testes de integracao para os endpoints de unidades."""

# pylint: disable=redefined-outer-name

import os
from datetime import UTC, datetime

import httpx
import pytest

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")

pytestmark = pytest.mark.integration


def _payload_unidade(**overrides):
    """Monta um payload unico de unidade para testes de integracao."""
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    payload = {
        "nome": f"Unidade Integracao {stamp}",
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
    payload.update(overrides)
    return payload


def _auth_headers() -> dict[str, str]:
    """Retorna headers de autenticacao ou pula o teste sem token."""
    if not API_AUTH_TOKEN:
        pytest.skip("Defina API_AUTH_TOKEN para rodar os testes de integracao.")
    return {"Authorization": f"Bearer {API_AUTH_TOKEN}"}


@pytest.fixture(name="api_client")
def fixture_api_client() -> httpx.Client:
    """Cria um cliente HTTP autenticado para os testes de unidades."""
    with httpx.Client(timeout=10.0, headers=_auth_headers()) as client:
        try:
            health = client.get(f"{BASE_URL}/")
            health.raise_for_status()
        except httpx.HTTPError as exc:
            pytest.skip(f"API de integracao indisponivel em {BASE_URL}: {exc}")
        yield client


@pytest.fixture(name="cleanup_ids")
def fixture_cleanup_ids():
    """Remove unidades criadas durante o teste ao final da execucao."""
    tracked = []
    yield tracked
    if not API_AUTH_TOKEN:
        return
    with httpx.Client(timeout=10.0, headers=_auth_headers()) as client:
        for unidade_id in reversed(tracked):
            client.delete(f"{BASE_URL}/unidades/{unidade_id}")


def test_criar_e_obter_unidade(api_client: httpx.Client, cleanup_ids) -> None:
    """Garante criacao e busca de unidade pela API real."""
    payload = _payload_unidade()

    create_response = api_client.post(f"{BASE_URL}/unidades/", json=payload)
    assert create_response.status_code == 201, create_response.text
    unidade_id = create_response.json()["id"]
    cleanup_ids.append(unidade_id)

    get_response = api_client.get(f"{BASE_URL}/unidades/{unidade_id}")

    assert get_response.status_code == 200, get_response.text
    body = get_response.json()
    assert body["id"] == unidade_id
    assert body["nome"] == payload["nome"]
    assert body["endereco"]["cidade"] == payload["endereco"]["cidade"]


def test_listar_unidades_retorna_200(api_client: httpx.Client) -> None:
    """Garante que a listagem de unidades responde com sucesso."""
    response = api_client.get(f"{BASE_URL}/unidades/")

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_obter_unidade_inexistente_retorna_404(api_client: httpx.Client) -> None:
    """Garante 404 ao buscar unidade inexistente."""
    response = api_client.get(f"{BASE_URL}/unidades/999999999")

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Unidade nao encontrada"


def test_atualizar_unidade_altera_dados_e_endereco(api_client: httpx.Client, cleanup_ids) -> None:
    """Garante atualizacao dos dados e endereco da unidade."""
    create_response = api_client.post(f"{BASE_URL}/unidades/", json=_payload_unidade())
    assert create_response.status_code == 201, create_response.text
    unidade_id = create_response.json()["id"]
    cleanup_ids.append(unidade_id)

    patch_response = api_client.patch(
        f"{BASE_URL}/unidades/{unidade_id}",
        json={
            "nome": "Unidade Integracao Atualizada",
            "endereco": {
                "cidade": "Campina Grande",
                "bairro": "Centro",
            },
        },
    )

    assert patch_response.status_code == 200, patch_response.text
    body = patch_response.json()
    assert body["nome"] == "Unidade Integracao Atualizada"
    assert body["endereco"]["cidade"] == "Campina Grande"
    assert body["endereco"]["bairro"] == "Centro"


def test_deletar_unidade_remove_e_get_retorna_404(
    api_client: httpx.Client,
    cleanup_ids,
) -> None:
    """Garante remocao de unidade e 404 na busca posterior."""
    create_response = api_client.post(f"{BASE_URL}/unidades/", json=_payload_unidade())
    assert create_response.status_code == 201, create_response.text
    unidade_id = create_response.json()["id"]

    delete_response = api_client.delete(f"{BASE_URL}/unidades/{unidade_id}")
    if delete_response.status_code != 204:
        cleanup_ids.append(unidade_id)

    assert delete_response.status_code == 204, delete_response.text

    get_response = api_client.get(f"{BASE_URL}/unidades/{unidade_id}")
    assert get_response.status_code == 404, get_response.text
    assert get_response.json()["detail"] == "Unidade nao encontrada"
