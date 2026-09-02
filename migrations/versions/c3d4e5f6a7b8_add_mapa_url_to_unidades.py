"""add mapa_url to unidades

Revision ID: c3d4e5f6a7b8
Revises: 9f3a2b1c0d4e
Create Date: 2026-06-15 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "9f3a2b1c0d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("unidades", sa.Column("mapa_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("unidades", "mapa_url")
