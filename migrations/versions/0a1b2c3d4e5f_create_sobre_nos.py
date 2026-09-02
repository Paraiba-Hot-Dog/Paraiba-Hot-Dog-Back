"""create sobre nos content

Revision ID: 0a1b2c3d4e5f
Revises: fda084f220cd, a1b2c3d4e5f6
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa


revision = "0a1b2c3d4e5f"
down_revision = ("fda084f220cd", "a1b2c3d4e5f6")
branch_labels = None
depends_on = None


TEXTO_PADRAO = (
    "Nascemos da paixão pela gastronomia de rua e pelo sabor autêntico da Paraíba. "
    "Desde 2015, levamos o melhor hot dog arretado para os brasilenses com qualidade, "
    "fartura e tradição. Nossa missão é servir ingredientes frescos, receitas exclusivas "
    "e um atendimento que faz você se sentir em casa."
)


def upgrade() -> None:
    op.create_table(
        "sobre_nos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("texto", sa.Text(), nullable=False),
    )
    op.bulk_insert(
        sa.table(
            "sobre_nos",
            sa.column("id", sa.Integer()),
            sa.column("texto", sa.Text()),
        ),
        [{"id": 1, "texto": TEXTO_PADRAO}],
    )


def downgrade() -> None:
    op.drop_table("sobre_nos")
