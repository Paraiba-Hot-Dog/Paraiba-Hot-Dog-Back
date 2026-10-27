"""Define a senha de um usuario no banco LOCAL para usar com AUTH_LOCAL=true.

Uso: PYTHONPATH=. python scripts/definir_senha_local.py <email> <senha>
No Docker: docker compose exec paraiba-hotdog-back env PYTHONPATH=/app python scripts/definir_senha_local.py <email> <senha>

So grava em banco local (localhost ou o container `postgres`); nunca toca o Supabase.
"""

import sys
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv()

import src.main  # noqa: F401  (registra todos os modelos, como no app)
from src.auth.local_auth import gerar_hash_senha
from src.database import SessionLocal, engine
from src.usuarios.model import Usuario

HOSTS_LOCAIS = {"localhost", "127.0.0.1", "postgres"}


def main() -> None:
    """Grava o hash da senha informada no usuario com o e-mail informado."""
    if len(sys.argv) != 3:
        sys.exit("Uso: PYTHONPATH=. python scripts/definir_senha_local.py <email> <senha>")

    host = engine.url.host
    if host not in HOSTS_LOCAIS:
        sys.exit(f"Banco '{host}' nao e local. Nada foi alterado.")

    email, senha = sys.argv[1], sys.argv[2]
    db = SessionLocal()
    try:
        usuario = db.query(Usuario).filter(Usuario.email == email).first()
        if not usuario:
            sys.exit(f"Usuario {email} nao existe no banco local.")

        usuario.senha = gerar_hash_senha(senha)
        if not usuario.auth_provider_id:
            usuario.auth_provider_id = f"local-{uuid4()}"
        db.commit()
        funcao = usuario.funcao.value
    finally:
        db.close()

    print(f"Senha local definida para {email} ({funcao}).")


if __name__ == "__main__":
    main()
