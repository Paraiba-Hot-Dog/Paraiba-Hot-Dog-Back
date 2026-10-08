"""create motivos_ajuste_pontos and clientes_ajustes_pontos

Revision ID: c9d1e2f3a4b5
Revises: b8e4c1a92f70
Create Date: 2026-10-03
"""

from alembic import op
import sqlalchemy as sa


revision = "c9d1e2f3a4b5"
down_revision = "b8e4c1a92f70"
branch_labels = None
depends_on = None

MOTIVOS_PADRAO = [
    {"descricao": "Correção de falha no ganho de pontos", "exige_observacao": False},
    {"descricao": "Correção de pontos lançados indevidamente", "exige_observacao": False},
    {"descricao": "Outro", "exige_observacao": True},
]


def upgrade() -> None:
    motivos = op.create_table(
        "motivos_ajuste_pontos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("descricao", sa.String(length=120), nullable=False, unique=True),
        sa.Column("exige_observacao", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.bulk_insert(motivos, MOTIVOS_PADRAO)

    op.create_table(
        "clientes_ajustes_pontos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column(
            "motivo_id",
            sa.Integer(),
            sa.ForeignKey("motivos_ajuste_pontos.id"),
            nullable=False,
        ),
        sa.Column("observacao", sa.String(length=255), nullable=True),
        sa.Column("pontos_anterior", sa.Integer(), nullable=False),
        sa.Column("pontos_atual", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuarios.id"), nullable=True),
        sa.Column("data_ajuste", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_clientes_ajustes_pontos_cliente_id",
        "clientes_ajustes_pontos",
        ["cliente_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_clientes_ajustes_pontos_cliente_id", table_name="clientes_ajustes_pontos")
    op.drop_table("clientes_ajustes_pontos")
    op.drop_table("motivos_ajuste_pontos")
