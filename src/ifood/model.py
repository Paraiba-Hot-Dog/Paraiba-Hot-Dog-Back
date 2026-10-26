"""Snapshots externos, inbox durável e comandos assíncronos."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base
# Register the FK target even when importing only the standalone worker.
import src.unidades.model  # pylint: disable=unused-import


def now():
    return datetime.now(timezone.utc)


class IfoodOrder(Base):
    __tablename__ = "ifood_orders"
    __table_args__ = (UniqueConstraint("merchant_id", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(100), index=True)
    external_id: Mapped[str] = mapped_column(String(100))
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidades.id"), index=True)
    state: Mapped[str] = mapped_column(String(40), default="PLACED")
    order_type: Mapped[str] = mapped_column(String(30), default="DELIVERY")
    delivered_by: Mapped[str | None] = mapped_column(String(30))
    display_id: Mapped[str] = mapped_column(String(100))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IfoodItem(Base):
    __tablename__ = "ifood_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("ifood_orders.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    payload: Mapped[dict] = mapped_column(JSON)


class IfoodEvent(Base):
    __tablename__ = "ifood_events"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(String(100), index=True)
    order_id: Mapped[str] = mapped_column(String(100), index=True)
    code: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    acknowledged: Mapped[bool] = mapped_column(default=False)
    processed: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str | None] = mapped_column(Text)


class IfoodCommand(Base):
    __tablename__ = "ifood_commands"
    __table_args__ = (UniqueConstraint("order_id", "request_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("ifood_orders.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    request_key: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(String(40), default="queued")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Events already received before a command cannot confirm it.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IfoodHealth(Base):
    __tablename__ = "ifood_health"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
