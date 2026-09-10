"""merge cardapio and main heads

Revision ID: fda084f220cd
Revises: 979dc0ad5a23, d16d5b3b524f
Create Date: 2026-05-19 01:22:08.025813

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fda084f220cd'
down_revision = ('979dc0ad5a23', 'd16d5b3b524f')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass