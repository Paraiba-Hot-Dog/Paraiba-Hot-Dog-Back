"""add motivo de ajuste de pontos 'Cliente realizou um novo pedido'

Revision ID: d4e7f1a2b3c6
Revises: c9d1e2f3a4b5
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "d4e7f1a2b3c6"
down_revision = "c9d1e2f3a4b5"
branch_labels = None
depends_on = None

DESCRICAO = "Cliente realizou um novo pedido"


def upgrade() -> None:
    motivos = sa.table(
        "motivos_ajuste_pontos",
        sa.column("descricao", sa.String),
        sa.column("exige_observacao", sa.Boolean),
    )
    op.bulk_insert(motivos, [{"descricao": DESCRICAO, "exige_observacao": False}])


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM motivos_ajuste_pontos WHERE descricao = :descricao")
        .bindparams(descricao=DESCRICAO)
    )
