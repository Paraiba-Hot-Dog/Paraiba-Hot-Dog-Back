"""create duvidas_frequentes table

Revision ID: dbf5d1df8599
Revises: a1b2c3d4e5f6
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = "dbf5d1df8599"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "duvidas_frequentes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pergunta", sa.String(length=255), nullable=False),
        sa.Column("resposta", sa.Text(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("duvidas_frequentes")
