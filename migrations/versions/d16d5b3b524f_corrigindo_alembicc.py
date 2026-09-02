"""corrigindo alembicc

Revision ID: d16d5b3b524f
Revises: 2d8a0f78b3a7, 9abe9133cc7d
Create Date: 2026-05-19 00:09:14.279272

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd16d5b3b524f'
down_revision = ('2d8a0f78b3a7', '9abe9133cc7d')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass