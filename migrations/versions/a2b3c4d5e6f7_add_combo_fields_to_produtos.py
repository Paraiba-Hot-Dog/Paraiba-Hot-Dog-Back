"""add combo fields to produtos and seed combo options

Revision ID: a2b3c4d5e6f7
Revises: f2a4b6c8d0e1
Create Date: 2026-11-05
"""

from alembic import op
import sqlalchemy as sa
from decimal import Decimal


revision = "a2b3c4d5e6f7"
down_revision = "f2a4b6c8d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Adiciona as colunas disponivel_no_combo e valor_adicional_combo na tabela produtos
    op.add_column(
        "produtos",
        sa.Column(
            "disponivel_no_combo",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "produtos",
        sa.Column(
            "valor_adicional_combo",
            sa.Numeric(precision=10, scale=2),
            server_default=sa.text("0.00"),
            nullable=False,
        ),
    )

    conn = op.get_bind()

    # 2. Remove variacoes de combo erroneamente adicionadas a bebidas/acompanhamentos
    conn.execute(
        sa.text(
            "DELETE FROM produto_variacoes "
            "WHERE tipo = 'combo' AND produto_id IN (19, 20, 21, 22, 23)"
        )
    )

    # 3. Semeia os itens que estao disponiveis como opcao no combo:
    # Refrigerante: disponivel no combo sem acrescimo
    conn.execute(
        sa.text(
            "UPDATE produtos SET disponivel_no_combo = true, valor_adicional_combo = 0.00 "
            "WHERE id = 19"
        )
    )
    # Sucos Integral: disponivel no combo sem acrescimo
    conn.execute(
        sa.text(
            "UPDATE produtos SET disponivel_no_combo = true, valor_adicional_combo = 0.00 "
            "WHERE id = 20"
        )
    )
    # Soda Italiana: disponivel no combo com acrescimo de R$ 5,00
    conn.execute(
        sa.text(
            "UPDATE produtos SET disponivel_no_combo = true, valor_adicional_combo = 5.00 "
            "WHERE id = 21"
        )
    )
    # Paraiba Chips: acompanhamento disponivel no combo sem acrescimo
    conn.execute(
        sa.text(
            "UPDATE produtos SET disponivel_no_combo = true, valor_adicional_combo = 0.00 "
            "WHERE id = 22"
        )
    )


def downgrade() -> None:
    op.drop_column("produtos", "valor_adicional_combo")
    op.drop_column("produtos", "disponivel_no_combo")

