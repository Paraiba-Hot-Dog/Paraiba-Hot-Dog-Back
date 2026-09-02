"""correção alembic

Revision ID: 979dc0ad5a23
Revises: 68aba97f921c, 9abe9133cc7d
Create Date: 2026-05-19 00:15:57.899362

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '979dc0ad5a23'
down_revision = ('68aba97f921c', '9abe9133cc7d')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass