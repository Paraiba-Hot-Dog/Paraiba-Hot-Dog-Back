"""add motivo de ajuste de pontos 'Cliente resgatou o bônus de fidelidade'

Revision ID: e5f8a2b4c7d9
Revises: d4e7f1a2b3c6
Create Date: 2026-10-05
"""

from alembic import op
import sqlalchemy as sa


revision = "e5f8a2b4c7d9"
down_revision = "d4e7f1a2b3c6"
branch_labels = None
depends_on = None

DESCRICAO = "Cliente resgatou o bônus de fidelidade"


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
