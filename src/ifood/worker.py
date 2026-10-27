"""Execute: python -m src.ifood.worker. Um consumidor por banco PostgreSQL."""
import logging
import time
from datetime import timedelta

import requests
from fastapi import HTTPException
from sqlalchemy import select, text

from src.config import settings
from src.database import SessionLocal, engine
from src.ifood.client import IfoodError, client
from src.ifood.model import IfoodCommand, IfoodEvent, IfoodHealth, IfoodOrder, now
from src.ifood.service import (DISPUTE_ACTIONS, cancellation_pending, allowed_actions, guard_merchant,
                               open_dispute, process_event, save_events, utc)

logger = logging.getLogger(__name__)
LOCK_ID = 736541208
# Order workflow guide: on 404 retry with exponential backoff for up to 10 minutes, never indefinitely.
RETRY_WINDOW = timedelta(minutes=10)
MAX_BACKOFF = 240


def valid_dispute_money(payload):
    body = payload.get("body") or {}
    if body.get("type") not in ("REFUND", "BENEFIT"):
        return True
    money = (body.get("metadata") or {}).get("amount") or {}
    value = money.get("value", "")
    return (isinstance(value, str) and value.isascii() and value.isdigit()
            and int(value) > 0 and money.get("currency") == "BRL")


def command_error(db, order, command):
    try:
        unit = guard_merchant(order.merchant_id)
    except HTTPException:
        unit = None
    if unit != order.unidade_id:
        return "Vínculo merchant/unidade mudou"
    if command.action in DISPUTE_ACTIONS:
        if not valid_dispute_money(command.payload):
            return "Formato monetário antigo ou inválido; envie uma nova resposta"
        current = open_dispute(db, order)
        if not current or current["disputeId"] != command.payload["disputeId"]:
            return "Negociação encerrada ou expirada antes do envio"
    elif cancellation_pending(db, order) or command.action not in allowed_actions(order):
        return "Estado ou modalidade mudou antes do envio"
    return None


def send_commands(db, api):
    # Recover possible process crashes after a request left the server.
    for c in db.scalars(select(IfoodCommand).where(IfoodCommand.state == "sending")):
        c.state, c.error = "indeterminate", "Worker reiniciado durante envio; aguardando evento"
    db.commit()
    for c in list(db.scalars(select(IfoodCommand).where(IfoodCommand.state == "queued").order_by(IfoodCommand.id))):
        order = db.scalar(select(IfoodOrder).where(IfoodOrder.id == c.order_id).with_for_update())
        error = command_error(db, order, c)
        if error:
            c.state, c.error = "rejected", error
            db.commit()
            continue
        dispute = c.action in DISPUTE_ACTIONS
        # Persist before network I/O: a restart must never blindly resend a mutation.
        c.state, c.sent_at, c.updated_at = "sending", now(), now()
        db.commit()
        try:
            if dispute:
                api.dispute(c.payload["disputeId"], c.payload["path"], c.payload.get("body"))
            else:
                api.command(order.external_id, c.action, c.payload)
            c.state, c.error = "pending", None
        except IfoodError as exc:
            c.state = "rejected" if 400 <= exc.status < 500 and exc.status not in (408, 429) else "indeterminate"
            c.error = str(exc)
            if exc.status == 429:
                # Server explicitly refused the request; retry at the next eligible cycle.
                c.state = "queued"
                c.sent_at = None
                db.commit()
                raise
        except (requests.RequestException, ValueError):
            c.state, c.error = "indeterminate", "Resposta não confirmada; aguardando reconciliação por evento"
        c.updated_at = now()
        db.commit()


class CycleDetails:
    """One current snapshot per order per cycle, shared even by ORDER_PATCHED events."""

    def __init__(self, api):
        self.api = api
        self.cache = {}

    def details(self, order_id):
        if order_id not in self.cache:
            self.cache[order_id] = self.api.details(order_id)
        return self.cache[order_id]


def defer_order(db, events, exc):
    """All pending events of an order share one durable retry window and counter."""
    attempts = max(event.attempts for event in events) + 1
    deadline = min(utc(event.received_at) for event in events) + RETRY_WINDOW
    expired = now() >= deadline
    delay = min(MAX_BACKOFF, 30 * 2 ** min(attempts - 1, 8))
    if getattr(exc, "status", None) == 429:
        delay = max(delay, exc.retry_after)
    retry_at = None if expired else min(now() + timedelta(seconds=delay), deadline)
    for event in events:
        event.attempts = attempts
        event.processed = expired
        event.next_attempt_at = retry_at
        event.error = ("Detalhes indisponíveis após 10 minutos; confira o pedido no Gestor iFood"
                       if expired else "Falha ao importar detalhes; nova tentativa agendada")
    db.commit()


def process_order_events(db, events, api):
    """Process one order; new events inherit the retry schedule of existing ones."""
    first = events[0]
    imported = db.scalar(select(IfoodOrder.id).where(
        IfoodOrder.merchant_id == first.merchant_id, IfoodOrder.external_id == first.order_id))
    if imported is None:
        abandoned = db.scalar(select(IfoodEvent).where(
            IfoodEvent.merchant_id == first.merchant_id, IfoodEvent.order_id == first.order_id,
            IfoodEvent.processed.is_(True), IfoodEvent.error.is_not(None), IfoodEvent.attempts > 0)
            .order_by(IfoodEvent.received_at).limit(1))
        if abandoned:
            for event in events:
                event.processed, event.error = True, abandoned.error
                event.attempts, event.next_attempt_at = abandoned.attempts, None
            db.commit()
            return False
    retries = [event for event in events if event.attempts]
    if retries:
        deadline = min(utc(event.received_at) for event in events) + RETRY_WINDOW
        if now() >= deadline:
            defer_order(db, events, None)
            return False
        retry_at = max((utc(event.next_attempt_at) for event in retries if event.next_attempt_at), default=now())
        if now() < retry_at:
            attempts = max(event.attempts for event in retries)
            for event in events:
                event.attempts, event.next_attempt_at = attempts, retry_at
            db.commit()
            return False
    for event in events:
        event_id = event.id
        try:
            process_event(db, event, api)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            db.rollback()
            # Do not log exception parameters: SQL errors can contain customer snapshots.
            logger.warning("Evento iFood %s falhou (%s)", event_id, type(exc).__name__)
            pending = [item for item in events if not item.processed]
            defer_order(db, pending, exc)
            return isinstance(exc, IfoodError) and getattr(exc, "status", None) == 429
    return False


def process_pending(db, api):
    pending = list(db.scalars(select(IfoodEvent).where(
        IfoodEvent.processed.is_(False),
        IfoodEvent.merchant_id.in_(list(settings.ifood_test_merchants)))
        .order_by(IfoodEvent.created_at, IfoodEvent.id)))
    groups = {}
    for event in pending:
        groups.setdefault((event.merchant_id, event.order_id), []).append(event)
    for events in groups.values():
        # The order identity includes the merchant, just like the persistent snapshot.
        if process_order_events(db, events, CycleDetails(api)):
            break


def cycle(db, api, *, include_commands=True):
    events = api.polling(list(settings.ifood_test_merchants))
    save_events(db, events)
    # Includes inbox records left unacknowledged by a previous process.
    unacked = list(db.scalars(select(IfoodEvent).where(IfoodEvent.acknowledged.is_(False),
                           IfoodEvent.merchant_id.in_(list(settings.ifood_test_merchants)))))
    for start in range(0, len(unacked), 2000):
        batch = unacked[start:start + 2000]
        api.acknowledge([e.id for e in batch])
        for e in batch:
            e.acknowledged = True
        db.commit()
    process_pending(db, api)
    if include_commands:
        send_commands(db, api)
    health = db.get(IfoodHealth, 1)
    if health is None:
        health = IfoodHealth(id=1)
        db.add(health)
    health.last_poll_at, health.error = now(), None
    db.commit()
    logger.info("Ciclo iFood concluído: %s evento(s) recebido(s)", len(events))


class WorkerSchedule:
    """Drain commands every second without increasing the iFood polling frequency."""

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.next_poll = 0
        self.next_commands = 0
        self.poll_delay = 30
        self.command_delay = 1

    def step(self, db, api):
        for task, interval in (("commands", 1), ("poll", 30)):
            if self.clock() < getattr(self, f"next_{task}"):
                continue
            started = self.clock()
            try:
                if task == "commands":
                    send_commands(db, api)
                else:
                    cycle(db, api, include_commands=False)
                delay = interval
            except (IfoodError, requests.RequestException) as exc:
                db.rollback()
                delay = max(min(300, getattr(self, f"{task.rstrip('s')}_delay") * 2),
                            getattr(exc, "retry_after", 30))
                health = db.get(IfoodHealth, 1) or IfoodHealth(id=1)
                health.error = "Falha de comunicação com iFood; aguardando nova tentativa"
                db.add(health)
                db.commit()
                logger.warning("Falha de comunicação (%s); próxima tentativa em %ss", task, delay)
                if getattr(exc, "status", None) == 429:
                    # Respect Retry-After across both schedules, including values over 300s.
                    cooldown = self.clock() + delay
                    self.next_poll = max(self.next_poll, cooldown)
                    self.next_commands = max(self.next_commands, cooldown)
            setattr(self, f"{task.rstrip('s')}_delay", delay)
            setattr(self, f"next_{task}", max(getattr(self, f"next_{task}"), started + delay))


def main():
    if not settings.ifood_enabled or not settings.ifood_test_merchants:
        raise SystemExit("Configure IFOOD_ENABLED e IFOOD_TEST_MERCHANTS com lojas de teste")
    if not settings.ifood_client_id or not settings.ifood_client_secret:
        raise SystemExit("Credenciais iFood de teste ausentes")
    if len(settings.ifood_test_merchants) > 100:
        raise SystemExit("Protótipo limitado a 100 merchants de teste")
    logging.basicConfig(level=logging.INFO)
    # Session advisory lock held on a dedicated connection for the worker lifetime.
    with engine.connect() as connection:
        if not connection.scalar(text("SELECT pg_try_advisory_lock(:id)"), {"id": LOCK_ID}):
            raise SystemExit("Já existe um worker iFood neste banco")
        logger.info("Worker iFood de testes iniciado: %s merchant(s)", len(settings.ifood_test_merchants))
        schedule = WorkerSchedule()
        try:
            while True:
                # Verify the lock connection is still alive before consuming.
                connection.execute(text("SELECT 1"))
                with SessionLocal() as db:
                    schedule.step(db, client)
                time.sleep(1)
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": LOCK_ID})


if __name__ == "__main__":
    main()
