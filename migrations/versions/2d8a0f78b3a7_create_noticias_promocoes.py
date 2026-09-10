"""create noticias_promocoes table

Revision ID: 2d8a0f78b3a7
Revises: 1f32fc4f41bc
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "2d8a0f78b3a7"
down_revision = "1f32fc4f41bc"
branch_labels = None
depends_on = None


noticia_promocao_type = postgresql.ENUM(
    "noticia",
    "promocao",
    name="tipo_noticia_promocao",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE tipo_noticia_promocao AS ENUM ('noticia', 'promocao');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END
        $$;
        """
    )

    op.create_table(
        "noticias_promocoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("imagem_url", sa.String(length=500), nullable=True),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("tipo", noticia_promocao_type, nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("noticias_promocoes")
    noticia_promocao_type.drop(op.get_bind(), checkfirst=True)
