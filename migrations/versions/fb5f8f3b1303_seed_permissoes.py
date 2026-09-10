"""seed permissoes

Revision ID: fb5f8f3b1303
Revises: cfc8005bd633
Create Date: 2026-05-14 02:11:52.415123

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fb5f8f3b1303'
down_revision = 'cfc8005bd633'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO permissoes (nome) VALUES
            ('anotar_pedidos'),
            ('cozinha'),
            ('dashboard'),
            ('configuracoes')
        ON CONFLICT (nome) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM permissoes WHERE nome IN ('anotar_pedidos', 'cozinha', 'dashboard', 'configuracoes')")