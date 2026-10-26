"""Execute: python -m src.ifood.worker. Um consumidor por banco PostgreSQL."""
import logging
import time
from datetime import timedelta

import requests
from fastapi import HTTPException
from sqlalchemy import or_, select, text

from src.config import settings
from src.database import SessionLocal, engine
from src.ifood.client import IfoodError, client
from src.ifood.model import IfoodCommand, IfoodEvent, IfoodHealth, IfoodOrder, now
from src.ifood.service import (cancellation_pending, allowed_actions, guard_merchant, process_event,
                               save_events, utc)

logger = logging.getLogger(__name__)
LOCK_ID = 736541208
# Order workflow guide: on 404 retry with exponential backoff for up to 10 minutes, never indefinitely.
RETRY_WINDOW = timedelta(minutes=10)
MAX_BACKOFF = 240


def send_commands(db, api):
    # Recover possible process crashes after a request left the server.
    for c in db.scalars(select(IfoodCommand).where(IfoodCommand.state == "sending")):
        c.state, c.error = "indeterminate", "Worker reiniciado durante envio; aguardando evento"
    db.commit()
    for c in list(db.scalars(select(IfoodCommand).where(IfoodCommand.state == "queued").order_by(IfoodCommand.id))):
        order = db.scalar(select(IfoodOrder).where(IfoodOrder.id == c.order_id).with_for_update())
        try:
            unit = guard_merchant(order.merchant_id)
        except HTTPException:
            unit = None
        if unit != order.unidade_id:
            c.state, c.error = "rejected", "Vínculo merchant/unidade mudou"
            db.commit()
            continue
        if cancellation_pending(db, order) or c.action not in allowed_actions(order):
            c.state, c.error = "rejected", "Estado ou modalidade mudou antes do envio"
            db.commit()
            continue
        # Persist before network I/O: a restart must never blindly resend a mutation.
        c.state, c.sent_at, c.updated_at = "sending", now(), now()
        db.commit()
        try:
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


def defer_event(db, event_id, exc):
    """Schedule the next attempt with exponential backoff or abandon after the retry window."""
    event = db.get(IfoodEvent, event_id)
    event.attempts += 1
    deadline = utc(event.received_at) + RETRY_WINDOW
    if now() >= deadline:
        event.processed, event.next_attempt_at = True, None
        event.error = "Detalhes indisponíveis após 10 minutos; confira o pedido no Gestor iFood"
    else:
        delay = min(MAX_BACKOFF, 30 * 2 ** (event.attempts - 1))
        if getattr(exc, "status", None) == 429:
            delay = max(delay, exc.retry_after)
        # The last attempt happens at the deadline, so the window is fully used but never exceeded.
        event.next_attempt_at = min(now() + timedelta(seconds=delay), deadline)
        event.error = "Falha ao importar detalhes; nova tentativa agendada"
    db.commit()


def process_pending(db, api):
    due = list(db.scalars(select(IfoodEvent).where(
        IfoodEvent.processed.is_(False),
        IfoodEvent.merchant_id.in_(list(settings.ifood_test_merchants)),
        or_(IfoodEvent.next_attempt_at.is_(None), IfoodEvent.next_attempt_at <= now()))
        .order_by(IfoodEvent.created_at, IfoodEvent.id)))
    for event in due:
        event_id = event.id
        try:
            process_event(db, event, api)
        # One faulty order must not hold back the others nor the queued commands.
        except Exception as exc:  # pylint: disable=broad-exception-caught
            db.rollback()
            logger.warning("Evento iFood %s falhou: %r", event_id, exc)
            defer_event(db, event_id, exc)
            if isinstance(exc, IfoodError) and exc.status == 429:
                break


def cycle(db, api):
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
    send_commands(db, api)
    health = db.get(IfoodHealth, 1)
    if health is None:
        health = IfoodHealth(id=1)
        db.add(health)
    health.last_poll_at, health.error = now(), None
    db.commit()
    logger.info("Ciclo iFood concluído: %s evento(s) recebido(s)", len(events))


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
        delay = 30
        try:
            while True:
                started = time.monotonic()
                try:
                    # Verify the lock connection is still alive before consuming.
                    connection.execute(text("SELECT 1"))
                    with SessionLocal() as db:
                        cycle(db, client)
                    delay = 30
                except (IfoodError, requests.RequestException) as exc:
                    delay = min(300, max(delay * 2, getattr(exc, "retry_after", 30)))
                    with SessionLocal() as db:
                        health = db.get(IfoodHealth, 1) or IfoodHealth(id=1)
                        health.error = "Falha de comunicação com iFood; aguardando nova tentativa"
                        db.add(health)
                        db.commit()
                    logger.warning("Falha de comunicação; próxima tentativa em %ss", delay)
                time.sleep(max(0, delay - (time.monotonic() - started)))
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": LOCK_ID})


if __name__ == "__main__":
    main()
