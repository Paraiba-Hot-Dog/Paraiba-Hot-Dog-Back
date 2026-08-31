"""Renomeia coluna keycloak_id para auth_provider_id na tabela usuarios.

Revision ID: a1b2c3d4e5f6
Revises: c3d4e5f6a7b8, 2d8a0f78b3a7
Create Date: 2026-08-30 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str]] = ("c3d4e5f6a7b8", "2d8a0f78b3a7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("usuarios", "keycloak_id", new_column_name="auth_provider_id")

    op.execute(
        "ALTER INDEX IF EXISTS ix_usuarios_keycloak_id RENAME TO ix_usuarios_auth_provider_id"
    )

    # RENAME CONSTRAINT nao suporta IF EXISTS, entao usamos DO block
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE usuarios RENAME CONSTRAINT uq_usuarios_keycloak_id TO uq_usuarios_auth_provider_id;
        EXCEPTION
            WHEN undefined_object THEN NULL;
        END $$;
    """)


def downgrade() -> None:
    op.alter_column("usuarios", "auth_provider_id", new_column_name="keycloak_id")

    op.execute(
        "ALTER INDEX IF EXISTS ix_usuarios_auth_provider_id RENAME TO ix_usuarios_keycloak_id"
    )

    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE usuarios RENAME CONSTRAINT uq_usuarios_auth_provider_id TO uq_usuarios_keycloak_id;
        EXCEPTION
            WHEN undefined_object THEN NULL;
        END $$;
    """)
