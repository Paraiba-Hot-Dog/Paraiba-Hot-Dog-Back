"""Cria uma conta local: LOCAL_ADMIN_PASSWORD=... python -m scripts.create_local_admin."""

import os

from passlib.hash import pbkdf2_sha256

from src.main import app  # Registra os modelos ORM.
from src.config import settings
from src.database import SessionLocal
from src.permissoes.model import Permissao
from src.usuarios.model import FuncaoUsuario, Usuario


def run():
    if not settings.local_auth_enabled:
        raise SystemExit("Ative LOCAL_AUTH_ENABLED no .env para criar a conta local.")
    password = os.environ.get("LOCAL_ADMIN_PASSWORD", "")
    if len(password) < 12:
        raise SystemExit("Defina LOCAL_ADMIN_PASSWORD com pelo menos 12 caracteres.")
    email = os.environ.get("LOCAL_ADMIN_EMAIL", "admin.local@example.com")
    with SessionLocal() as db:
        if db.query(Usuario).filter(Usuario.email == email).first():
            raise SystemExit("Conta ja existe; nenhuma alteracao realizada.")
        usuario = Usuario(
            nome="Administrador Local", email=email,
            senha=pbkdf2_sha256.hash(password),
            funcao=FuncaoUsuario.administrador,
        )
        usuario.permissoes = db.query(Permissao).all()
        db.add(usuario)
        db.commit()
    print(f"Administrador local criado: {email}")


if __name__ == "__main__":
    run()
