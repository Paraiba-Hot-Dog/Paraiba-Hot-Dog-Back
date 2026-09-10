"""create recuperacao senha tokens

Revision ID: 9f3a2b1c0d4e
Revises: b1c2d3e4f5a6
Create Date: 2026-06-14 21:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


revision = "9f3a2b1c0d4e"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recuperacao_senha_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recuperacao_senha_tokens_token_hash",
        "recuperacao_senha_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_recuperacao_senha_tokens_usuario_id",
        "recuperacao_senha_tokens",
        ["usuario_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_recuperacao_senha_tokens_usuario_id", table_name="recuperacao_senha_tokens")
    op.drop_index("ix_recuperacao_senha_tokens_token_hash", table_name="recuperacao_senha_tokens")
    op.drop_table("recuperacao_senha_tokens")
