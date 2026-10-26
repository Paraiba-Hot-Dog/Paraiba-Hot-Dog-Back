"""Bounded retry of iFood order details per event."""
from alembic import op
import sqlalchemy as sa

revision = "20261026_ifood_retry"
down_revision = "20261026_ifood"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ifood_events", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ifood_events", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("ifood_events", "next_attempt_at")
    op.drop_column("ifood_events", "attempts")
