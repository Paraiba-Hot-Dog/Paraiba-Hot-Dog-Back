"""avaliacoes: indices nas fks e on delete cascade em unidade_id

Revision ID: b7d9f1a3c5e2
Revises: f1a2b3c4d5e6
Create Date: 2026-09-07
"""

from alembic import op


revision = "b7d9f1a3c5e2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "avaliacoes_unidade_id_fkey", "avaliacoes", type_="foreignkey"
    )
    op.create_foreign_key(
        "avaliacoes_unidade_id_fkey",
        "avaliacoes",
        "unidades",
        ["unidade_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_avaliacoes_cliente_id", "avaliacoes", ["cliente_id"])
    op.create_index("ix_avaliacoes_unidade_id", "avaliacoes", ["unidade_id"])


def downgrade() -> None:
    op.drop_index("ix_avaliacoes_unidade_id", table_name="avaliacoes")
    op.drop_index("ix_avaliacoes_cliente_id", table_name="avaliacoes")
    op.drop_constraint(
        "avaliacoes_unidade_id_fkey", "avaliacoes", type_="foreignkey"
    )
    op.create_foreign_key(
        "avaliacoes_unidade_id_fkey",
        "avaliacoes",
        "unidades",
        ["unidade_id"],
        ["id"],
    )
