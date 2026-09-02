"""add fk usuarios unidade_id

Revision ID: 2b4d6f8a9c11
Revises: 1f32fc4f41bc
Create Date: 2026-05-17 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2b4d6f8a9c11"
down_revision = "1f32fc4f41bc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE usuarios
            SET unidade_id = NULL
            WHERE unidade_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1
                FROM unidades
                WHERE unidades.id = usuarios.unidade_id
              )
            """
        )
    )
    op.create_foreign_key(
        "fk_usuarios_unidade_id",
        "usuarios",
        "unidades",
        ["unidade_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_usuarios_unidade_id", "usuarios", type_="foreignkey")
