"""Isolated test integration inbox, snapshots and command ledger."""
from alembic import op
import sqlalchemy as sa

revision = "20261026_ifood"
down_revision = "e5f8a2b4c7d9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("ifood_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("merchant_id", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("unidade_id", sa.Integer(), sa.ForeignKey("unidades.id"), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("order_type", sa.String(30), nullable=False),
        sa.Column("delivered_by", sa.String(30)),
        sa.Column("display_id", sa.String(100), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("merchant_id", "external_id"))
    op.create_table("ifood_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("ifood_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False))
    op.create_table("ifood_events",
        sa.Column("id", sa.String(100), primary_key=True),
        sa.Column("merchant_id", sa.String(100), nullable=False),
        sa.Column("order_id", sa.String(100), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text()))
    op.create_table("ifood_commands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("ifood_orders.id"), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", "request_key"))
    op.create_table("ifood_health",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_poll_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()))
    for table, fields in {"ifood_orders": ["merchant_id", "unidade_id"],
                          "ifood_items": ["order_id"], "ifood_events": ["merchant_id", "order_id"],
                          "ifood_commands": ["order_id"]}.items():
        for field in fields:
            op.create_index(f"ix_{table}_{field}", table, [field])


def downgrade():
    for table in ("ifood_health", "ifood_commands", "ifood_events", "ifood_items", "ifood_orders"):
        op.drop_table(table)
