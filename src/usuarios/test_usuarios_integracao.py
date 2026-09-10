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


def test_atualizar_usuario_com_unidade_inexistente_retorna_404(
    api_client: httpx.Client,
    cleanup_ids,
) -> None:
    """Garante 404 ao atualizar usuario com unidade inexistente."""
    unidade_id = _create_unidade()
    cleanup_ids["unidades"].append(unidade_id)
    create_payload = {
        "nome": "Usuario Atualizacao",
        "email": _unique_email("usuario.update"),
        "senha": "12345678",
        "funcao": "caixa",
        "unidade_id": unidade_id,
        "permissao_ids": [],
    }

    create_resp = api_client.post(f"{BASE_URL}/usuarios/", json=create_payload)
    assert create_resp.status_code == 201, create_resp.text
    usuario_id = create_resp.json()["id"]
    cleanup_ids["usuarios"].append(usuario_id)
    patch_resp = api_client.patch(
        f"{BASE_URL}/usuarios/{usuario_id}",
        json={"unidade_id": 999999},
    )

    assert patch_resp.status_code == 404, patch_resp.text
    assert patch_resp.json()["detail"] == "Unidade nao encontrada"


def test_listar_usuarios_retorna_200(api_client: httpx.Client) -> None:
    """Garante que a listagem de usuarios responde com sucesso."""
    response = api_client.get(f"{BASE_URL}/usuarios/")

    assert response.status_code == 200, response.text
    assert isinstance(response.json(), list)


def test_obter_usuario_existente_retorna_200(api_client: httpx.Client, cleanup_ids) -> None:
    """Garante busca de usuario existente pela API real."""
    unidade_id = _create_unidade()
    cleanup_ids["unidades"].append(unidade_id)
    payload = {
        "nome": "Usuario Get",
        "email": _unique_email("usuario.get"),
        "senha": "12345678",
        "funcao": "caixa",
        "unidade_id": unidade_id,
        "permissao_ids": [],
    }

    create_resp = api_client.post(f"{BASE_URL}/usuarios/", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    usuario_id = create_resp.json()["id"]
    cleanup_ids["usuarios"].append(usuario_id)
    get_resp = api_client.get(f"{BASE_URL}/usuarios/{usuario_id}")

    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["id"] == usuario_id
    assert body["email"] == payload["email"]


def test_obter_usuario_inexistente_retorna_404(api_client: httpx.Client) -> None:
    """Garante 404 ao buscar usuario inexistente."""
    response = api_client.get(f"{BASE_URL}/usuarios/999999999")

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Usuario nao encontrado"


def test_deletar_usuario_remove_e_get_retorna_404(api_client: httpx.Client, cleanup_ids) -> None:
    """Garante remocao de usuario e 404 na busca posterior."""
    unidade_id = _create_unidade()
    cleanup_ids["unidades"].append(unidade_id)
    payload = {
        "nome": "Usuario Delete",
        "email": _unique_email("usuario.delete"),
        "senha": "12345678",
        "funcao": "caixa",
        "unidade_id": unidade_id,
        "permissao_ids": [],
    }

    create_resp = api_client.post(f"{BASE_URL}/usuarios/", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    usuario_id = create_resp.json()["id"]
    delete_resp = api_client.delete(f"{BASE_URL}/usuarios/{usuario_id}")
    assert delete_resp.status_code == 204, delete_resp.text
    get_resp = api_client.get(f"{BASE_URL}/usuarios/{usuario_id}")

    assert get_resp.status_code == 404, get_resp.text
    assert get_resp.json()["detail"] == "Usuario nao encontrado"
