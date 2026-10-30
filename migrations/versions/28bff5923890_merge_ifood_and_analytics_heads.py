"""merge ifood and analytics heads

Revision ID: 28bff5923890
Revises: 20261026_ifood_retry, 8d4f68e6ba5f
Create Date: 2026-10-30 16:21:59.984572

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '28bff5923890'
down_revision = ('20261026_ifood_retry', '8d4f68e6ba5f')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass