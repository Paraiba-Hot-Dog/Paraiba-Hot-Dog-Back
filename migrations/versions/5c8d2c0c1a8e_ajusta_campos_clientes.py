"""ajusta campos clientes

Revision ID: 5c8d2c0c1a8e
Revises: 1f32fc4f41bc
Create Date: 2026-05-18 12:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5c8d2c0c1a8e"
down_revision = "2b4d6f8a9c11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "clientes",
        "telefone",
        existing_type=sa.String(length=20),
        nullable=False,
    )
    op.create_unique_constraint(
        op.f("uq_clientes_telefone"), "clientes", ["telefone"])
    op.create_unique_constraint(
        op.f("uq_clientes_email"), "clientes", ["email"])
    op.alter_column(
        "clientes",
        "data_cadastro",
        existing_type=sa.String(length=20),
        type_=sa.DateTime(),
        server_default=sa.text("now()"),
        nullable=False,
        postgresql_using="data_cadastro::timestamp",
    )


def downgrade() -> None:
    op.alter_column(
        "clientes",
        "data_cadastro",
        existing_type=sa.DateTime(),
        type_=sa.String(length=20),
        server_default=None,
        nullable=False,
        postgresql_using="data_cadastro::text",
    )
    op.drop_constraint(op.f("uq_clientes_email"), "clientes", type_="unique")
    op.drop_constraint(op.f("uq_clientes_telefone"),
                       "clientes", type_="unique")
    op.alter_column(
        "clientes",
        "telefone",
        existing_type=sa.String(length=20),
        nullable=True,
    )
