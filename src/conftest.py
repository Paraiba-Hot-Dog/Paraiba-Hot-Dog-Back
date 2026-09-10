"""Configuracao compartilhada dos testes."""

import pytest

from src.main import app
from src.security import get_current_user


@pytest.fixture(autouse=True)
def override_authentication():
    """Usa um usuario autenticado fake nos testes unitarios com TestClient."""

    def _get_current_user():
        """Retorna um usuario fake para substituir a autenticacao real nos testes."""
        return {
            "sub": "test-user",
            "preferred_username": "test",
            "email": "test@example.com",
            "roles": ["test", "administrador"],
        }

    app.dependency_overrides[get_current_user] = _get_current_user
    yield
    app.dependency_overrides.pop(get_current_user, None)
