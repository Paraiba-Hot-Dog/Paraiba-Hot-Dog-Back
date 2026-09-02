"""ajusta cardapio e disponibilidade produtos

Revision ID: 4b6a1c9d2e10
Revises: fda084f220cd
Create Date: 2026-05-22 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "4b6a1c9d2e10"
down_revision = "fda084f220cd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "produtos",
        sa.Column(
            "pontos_fidelidade_por_unidade",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "produtos",
        sa.Column(
            "disponivel_todas_unidades",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )

    op.create_table(
        "produto_unidades",
        sa.Column("produto_id", sa.Integer(), nullable=False),
        sa.Column("unidade_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["produto_id"], ["produtos.id"]),
        sa.ForeignKeyConstraint(["unidade_id"], ["unidades.id"]),
        sa.PrimaryKeyConstraint("produto_id", "unidade_id"),
    )

    op.add_column("produto_variacoes", sa.Column("nome", sa.String(length=80), nullable=True))
    op.execute(
        """
        UPDATE produto_variacoes
        SET nome = COALESCE(label_combo, tipo::text)
        """
    )
    op.alter_column("produto_variacoes", "nome", nullable=False)
    op.add_column(
        "produto_variacoes",
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.drop_column("produto_variacoes", "preco_combo")
    op.drop_column("produto_variacoes", "label_combo")


def downgrade() -> None:
    op.add_column("produto_variacoes", sa.Column("label_combo", sa.String(length=50), nullable=True))
    op.add_column("produto_variacoes", sa.Column("preco_combo", sa.Numeric(precision=10, scale=2), nullable=True))
    op.drop_column("produto_variacoes", "ativo")
    op.drop_column("produto_variacoes", "nome")
    op.drop_table("produto_unidades")
    op.drop_column("produtos", "disponivel_todas_unidades")
    op.drop_column("produtos", "pontos_fidelidade_por_unidade")
