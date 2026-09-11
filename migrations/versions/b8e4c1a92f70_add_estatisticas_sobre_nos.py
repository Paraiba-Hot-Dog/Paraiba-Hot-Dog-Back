"""add estatisticas to sobre_nos

Revision ID: b8e4c1a92f70
Revises: 7a1f2e9c4b3d
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = "b8e4c1a92f70"
down_revision = "7a1f2e9c4b3d"
branch_labels = None
depends_on = None

ESTATISTICAS_PADRAO = [
    {"valor": "10+", "legenda": "Anos de funcionamento"},
    {"valor": "4,9", "legenda": "Avaliação média"},
    {"valor": "3", "legenda": "Unidades"},
]


def upgrade() -> None:
    op.add_column("sobre_nos", sa.Column("estatisticas", sa.JSON(), nullable=True))
    sobre_nos = sa.table("sobre_nos", sa.column("estatisticas", sa.JSON()))
    op.execute(sobre_nos.update().values(estatisticas=ESTATISTICAS_PADRAO))
    op.alter_column("sobre_nos", "estatisticas", nullable=False)


def downgrade() -> None:
    op.drop_column("sobre_nos", "estatisticas")
