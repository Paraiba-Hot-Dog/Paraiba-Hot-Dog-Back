"""add keycloak id to usuarios

Revision ID: 7e2a9c4d6f10
Revises: d16d5b3b524f
Create Date: 2026-05-23 12:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "7e2a9c4d6f10"
down_revision = "d16d5b3b524f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("keycloak_id", sa.String(length=64), nullable=True))
    op.create_index("ix_usuarios_keycloak_id", "usuarios", ["keycloak_id"], unique=True)
    op.alter_column("usuarios", "senha", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    op.alter_column("usuarios", "senha", existing_type=sa.String(length=255), nullable=False)
    op.drop_index("ix_usuarios_keycloak_id", table_name="usuarios")
    op.drop_column("usuarios", "keycloak_id")
