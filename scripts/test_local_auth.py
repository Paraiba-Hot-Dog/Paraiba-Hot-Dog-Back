"""Verificacoes isoladas: python -m unittest scripts.test_local_auth."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from jose import jwt
from passlib.hash import pbkdf2_sha256

from src.auth import local_auth
from src.config import settings


class LocalAuthTests(unittest.TestCase):
    def setUp(self):
        self.enabled = patch.object(settings, "local_auth_enabled", True)
        self.secret = patch.object(settings, "local_auth_secret", "test-secret-" * 4)
        self.enabled.start()
        self.secret.start()
        self.addCleanup(self.enabled.stop)
        self.addCleanup(self.secret.stop)
        self.db = MagicMock()
        self.db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
            id=1, auth_provider_id=None, email="admin.local@example.com",
            senha=pbkdf2_sha256.hash("test-password"),
            funcao=SimpleNamespace(value="administrador"),
        )

    def test_login_and_signed_token(self):
        result = local_auth.login(self.db, "admin.local@example.com", "test-password")
        claims = local_auth.decode_token(result["access_token"])
        self.assertEqual(claims["user_metadata"]["funcao"], "administrador")
        self.assertEqual(claims["sub"], "local:1")

    def test_wrong_password_and_unknown_user(self):
        with self.assertRaises(HTTPException) as error:
            local_auth.login(self.db, "admin.local@example.com", "wrong")
        self.assertEqual(error.exception.status_code, 401)
        self.db.query.return_value.filter.return_value.first.return_value = None
        with self.assertRaises(HTTPException):
            local_auth.login(self.db, "unknown@example.com", "test-password")

    def test_invalid_tokens(self):
        claims = dict(sub="local:1", exp=9999999999, iss=local_auth.ISSUER, aud=local_auth.AUDIENCE)
        for changes, secret in [({"exp": 1}, settings.local_auth_secret),
                                ({"iss": "other"}, settings.local_auth_secret),
                                ({"aud": "other"}, settings.local_auth_secret),
                                ({}, "wrong-key")]:
            token = jwt.encode({**claims, **changes}, secret, algorithm="HS256")
            with self.assertRaises(HTTPException) as error:
                local_auth.decode_token(token)
            self.assertEqual(error.exception.status_code, 401)

    def test_disabled_or_missing_secret(self):
        for enabled, secret in [(False, "s" * 40), (True, "")]:
            with patch.object(settings, "local_auth_enabled", enabled), patch.object(settings, "local_auth_secret", secret):
                with self.assertRaises(HTTPException) as error:
                    local_auth.login(self.db, "admin.local@example.com", "test-password")
                self.assertEqual(error.exception.status_code, 503)
