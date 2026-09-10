"""add pedidos

Revision ID: 6d2e8b4f91a0
Revises: 4b6a1c9d2e10
Create Date: 2026-05-22 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "6d2e8b4f91a0"
down_revision = "4b6a1c9d2e10"
branch_labels = None
depends_on = None


status_conta_pedido = sa.Enum(
    "aberto",
    "pago",
    "cancelado",
    name="status_conta_pedido",
)
status_cozinha_item_pedido = sa.Enum(
    "aberto",
    "preparando",
    "entregue",
    "cancelado",
    name="status_cozinha_item_pedido",
)
forma_pagamento = sa.Enum(
    "pix",
    "credito",
    "debito",
    "dinheiro",
    name="forma_pagamento",
)


def upgrade() -> None:
    op.create_table(
        "pedidos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("unidade_id", sa.Integer(), nullable=False),
        sa.Column("nome_comanda", sa.String(length=120), nullable=False),
        sa.Column("cliente_id", sa.Integer(), nullable=True),
        sa.Column("status", status_conta_pedido, nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("desconto_fidelidade", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("forma_pagamento", forma_pagamento, nullable=True),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("pontos_fidelidade_utilizados", sa.Integer(), nullable=False),
        sa.Column("pontos_fidelidade_creditados", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("fechado_em", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["cliente_id"], ["clientes.id"]),
        sa.ForeignKeyConstraint(["unidade_id"], ["unidades.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "itens_pedido",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pedido_id", sa.Integer(), nullable=False),
        sa.Column("produto_variacao_id", sa.Integer(), nullable=False),
        sa.Column("produto_id", sa.Integer(), nullable=False),
        sa.Column("produto_nome", sa.String(length=255), nullable=False),
        sa.Column("produto_variacao_nome", sa.String(length=80), nullable=True),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("preco_unitario", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("observacao", sa.Text(), nullable=True),
        sa.Column("status", status_cozinha_item_pedido, nullable=False),
        sa.Column("lote", sa.Integer(), nullable=False),
        sa.Column("motivo_cancelamento", sa.Text(), nullable=True),
        sa.Column("cancelado_em", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["pedido_id"], ["pedidos.id"]),
        sa.ForeignKeyConstraint(["produto_id"], ["produtos.id"]),
        sa.ForeignKeyConstraint(["produto_variacao_id"], ["produto_variacoes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "item_pedido_adicionais",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_pedido_id", sa.Integer(), nullable=False),
        sa.Column("adicional_id", sa.Integer(), nullable=True),
        sa.Column("nome", sa.String(length=255), nullable=False),
        sa.Column("preco", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["adicional_id"], ["produto_adicionais.id"]),
        sa.ForeignKeyConstraint(["item_pedido_id"], ["itens_pedido.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("item_pedido_adicionais")
    op.drop_table("itens_pedido")
    op.drop_table("pedidos")

    forma_pagamento.drop(op.get_bind(), checkfirst=True)
    status_cozinha_item_pedido.drop(op.get_bind(), checkfirst=True)
    status_conta_pedido.drop(op.get_bind(), checkfirst=True)
