"""create avaliacoes table

Revision ID: f1a2b3c4d5e6
Revises: 0a1b2c3d4e5f
Create Date: 2026-09-06
"""

from alembic import op
import sqlalchemy as sa


revision = "f1a2b3c4d5e6"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "avaliacoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome_cliente", sa.String(length=120), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("estrelas", sa.Integer(), nullable=False),
        sa.Column(
            "ativo", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.CheckConstraint(
            "estrelas BETWEEN 1 AND 5", name="ck_avaliacoes_estrelas_1_5"
        ),
    )


def downgrade() -> None:
    op.drop_table("avaliacoes")
