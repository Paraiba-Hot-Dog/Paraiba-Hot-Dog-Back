"""create sobre_nos_imagens table

Revision ID: 7a1f2e9c4b3d
Revises: a1b2c3d4e5f6
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa


revision = "7a1f2e9c4b3d"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sobre_nos_imagens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("imagem_url", sa.String(length=500), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("posicao", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sobre_nos_imagens")
