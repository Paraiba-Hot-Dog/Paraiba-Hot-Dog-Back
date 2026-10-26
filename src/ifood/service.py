"""Regras de importação, projeção e comandos do protótipo."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select

from src.config import settings
from src.ifood.model import IfoodCommand, IfoodEvent, IfoodItem, IfoodOrder, now

STATES = {"PLACED": 0, "CONFIRMED": 1, "PREPARATION_STARTED": 2,
          "READY_TO_PICKUP": 3, "DISPATCHED": 4, "CONCLUDED": 5, "CANCELLED": 6}
ALIASES = {"PLC": "PLACED", "CFM": "CONFIRMED", "PRS": "PREPARATION_STARTED",
           "RTP": "READY_TO_PICKUP", "DSP": "DISPATCHED", "CON": "CONCLUDED", "CAN": "CANCELLED",
           "CAR": "CANCELLATION_REQUESTED", "CARF": "CANCELLATION_REQUEST_FAILED", "OPA": "ORDER_PATCHED",
           "RPS": "RECOMMENDED_PREPARATION_START", "ADR": "ASSIGN_DRIVER", "GTO": "GOING_TO_ORIGIN",
           "AAO": "ARRIVED_AT_ORIGIN", "CLT": "COLLECTED", "AAD": "ARRIVED_AT_DESTINATION",
           "HSD": "HANDSHAKE_DISPUTE", "HSS": "HANDSHAKE_SETTLEMENT", "DAR": "DELIVERY_ADDRESS_CHANGE_REQUESTED"}
ACTIONS = {"confirm": ("PLACED",), "startPreparation": ("CONFIRMED",),
           "readyToPickup": ("CONFIRMED", "PREPARATION_STARTED"),
           "dispatch": ("READY_TO_PICKUP",),
           "requestCancellation": ("PLACED", "CONFIRMED", "PREPARATION_STARTED", "READY_TO_PICKUP", "DISPATCHED")}
EXPECTED = {"confirm": "CONFIRMED", "startPreparation": "PREPARATION_STARTED",
            "readyToPickup": "READY_TO_PICKUP", "dispatch": "DISPATCHED",
            "requestCancellation": "CANCELLED"}
ACTIVE_COMMANDS = ("queued", "sending", "pending", "indeterminate")
TRACKING = {"ASSIGN_DRIVER", "GOING_TO_ORIGIN", "ARRIVED_AT_ORIGIN", "COLLECTED",
            "ARRIVED_AT_DESTINATION", "DELIVERY_RETURNING_TO_ORIGIN", "DELIVERY_RETURNED_TO_ORIGIN"}


def utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def guard_merchant(merchant_id):
    if not settings.ifood_enabled:
        raise HTTPException(503, "Integração de testes desativada")
    unit = settings.ifood_test_merchants.get(merchant_id)
    if not unit:
        raise HTTPException(403, "Merchant não permitido no ambiente de testes")
    return unit


def preparation_at(order):
    value = order.payload.get("preparationStartDateTime")
    return utc(value) if value else None


def allowed_actions(order):
    actions = [action for action, states in ACTIONS.items() if order.state in states]
    if order.order_type != "DELIVERY" or order.delivered_by != "MERCHANT":
        actions = [action for action in actions if action != "dispatch"]
    start = preparation_at(order)
    if start and now() < start:
        actions = [action for action in actions if action not in ("startPreparation", "readyToPickup", "dispatch")]
    return actions


def save_events(db, events):
    for payload in events:
        merchant = payload.get("merchantId")
        guard_merchant(merchant)
        if db.get(IfoodEvent, payload["id"]):
            continue
        db.add(IfoodEvent(id=payload["id"], merchant_id=merchant,
                         order_id=payload["orderId"],
                         code=payload.get("fullCode") or ALIASES.get(payload["code"], payload["code"]),
                         payload=payload, created_at=utc(payload["createdAt"])))
    db.commit()


def update_snapshot(db, order, data):
    # Float JSON numbers are converted through strings, never used for arithmetic.
    order.payload = data
    order.order_type = data.get("orderType", "DELIVERY")
    order.delivered_by = data.get("delivery", {}).get("deliveredBy")
    order.display_id = str(data.get("displayId") or order.external_id)
    order.total = Decimal(str(data.get("total", {}).get("orderAmount", 0)))
    db.query(IfoodItem).filter_by(order_id=order.id).delete()
    for i, item in enumerate(data.get("items", [])):
        db.add(IfoodItem(order_id=order.id, external_id=str(item.get("id", i)),
                         name=item.get("name", "Item"), quantity=Decimal(str(item.get("quantity", 1))),
                         unit_price=Decimal(str(item.get("unitPrice", 0))), payload=item))


def process_event(db, event, api):
    unit = guard_merchant(event.merchant_id)
    order = db.scalar(select(IfoodOrder).where(IfoodOrder.merchant_id == event.merchant_id,
                                              IfoodOrder.external_id == event.order_id).with_for_update())
    if order is None:
        data = api.details(event.order_id)
        if data.get("merchant", {}).get("id") != event.merchant_id:
            raise ValueError("Merchant dos detalhes não corresponde ao evento")
        order = IfoodOrder(merchant_id=event.merchant_id, external_id=event.order_id,
                           unidade_id=unit, state="UNKNOWN", display_id=event.order_id,
                           created_at=utc(data.get("createdAt", event.created_at)))
        db.add(order)
        db.flush()
        update_snapshot(db, order, data)
    if order.unidade_id != unit:
        raise ValueError("Vínculo merchant/unidade mudou")
    code = event.code
    if code == "RECOMMENDED_PREPARATION_START":
        start = event.payload.get("metadata", {}).get("expectedPreparationStartTimestamp")
        if start:
            order.payload = {**order.payload, "preparationStartDateTime": start}
    if code == "ORDER_PATCHED":
        data = api.details(event.order_id)
        if data.get("merchant", {}).get("id") != event.merchant_id:
            raise ValueError("Merchant inválido")
        update_snapshot(db, order, data)
    if code in STATES:
        fresh = order.last_event_at is None or utc(event.created_at) >= utc(order.last_event_at)
        terminal = order.state in ("CONCLUDED", "CANCELLED")
        if fresh and ((not terminal and STATES[code] >= STATES.get(order.state, 0)) or code == "CANCELLED"):
            order.state = code
            order.last_event_at = event.created_at
    settle_commands(db, order, event)
    order.synced_at = now()
    event.processed, event.error = True, None
    db.commit()


def settle_commands(db, order, event):
    code = event.code
    for command in db.scalars(select(IfoodCommand).where(
            IfoodCommand.order_id == order.id, IfoodCommand.state.in_(ACTIVE_COMMANDS))):
        # queued commands have not been sent and must still be checked before sending.
        if command.sent_at is None or utc(event.created_at) < utc(command.sent_at):
            continue
        if code == EXPECTED[command.action]:
            command.state, command.error = "confirmed", None
        elif code == "CANCELLATION_REQUEST_FAILED" and command.action == "requestCancellation":
            command.state, command.error = "rejected", "Cancelamento rejeitado pelo iFood"
        elif code == "CANCELLED":
            command.state, command.error = "rejected", "Pedido cancelado no iFood"
        elif code in STATES and STATES[code] > STATES[EXPECTED[command.action]]:
            command.state, command.error = "superseded", "Estado avançou no iFood; confira o histórico"
        command.updated_at = now()


def cancellation_pending(db, order):
    if order.state in ("CANCELLED", "CONCLUDED"):
        return False
    latest = db.scalar(select(IfoodEvent).where(
        IfoodEvent.merchant_id == order.merchant_id, IfoodEvent.order_id == order.external_id,
        IfoodEvent.code.in_(("CANCELLATION_REQUESTED", "CANCELLATION_REQUEST_FAILED", "CANCELLED")))
        .order_by(IfoodEvent.created_at.desc(), IfoodEvent.received_at.desc()).limit(1))
    return latest is not None and latest.code == "CANCELLATION_REQUESTED"


def enqueue(db, order_id, action, key, payload):
    order = db.scalar(select(IfoodOrder).where(IfoodOrder.id == order_id).with_for_update())
    if not order:
        raise HTTPException(404, "Pedido não encontrado")
    if guard_merchant(order.merchant_id) != order.unidade_id:
        raise HTTPException(409, "Vínculo merchant/unidade mudou; revise a configuração")
    existing = db.scalar(select(IfoodCommand).where(IfoodCommand.order_id == order.id,
                                                   IfoodCommand.request_key == key))
    if existing:
        if existing.action != action or existing.payload != payload:
            raise HTTPException(409, "Chave de idempotência já usada por outra ação")
        return existing
    active = db.scalar(select(IfoodCommand).where(IfoodCommand.order_id == order.id,
                                                  IfoodCommand.state.in_(ACTIVE_COMMANDS)))
    if active:
        raise HTTPException(409, "Há uma operação pendente. Aguarde a reconciliação.")
    if cancellation_pending(db, order):
        raise HTTPException(409, "Cancelamento solicitado no iFood; aguarde o resultado")
    if action not in allowed_actions(order):
        raise HTTPException(409, "Ação não permitida para o estado, modalidade ou horário do pedido")
    command = IfoodCommand(order_id=order.id, action=action, request_key=key, payload=payload)
    db.add(command)
    db.commit()
    db.refresh(command)
    return command


def command_dict(command):
    return {"id": command.id, "action": command.action, "state": command.state,
            "error": command.error, "created_at": command.created_at, "updated_at": command.updated_at}


def order_dict(db, order, detail=False):
    commands = list(db.scalars(select(IfoodCommand).where(IfoodCommand.order_id == order.id)
                              .order_by(IfoodCommand.id.desc())))
    pending = next((c for c in commands if c.state in ACTIVE_COMMANDS), None)
    events = list(db.scalars(select(IfoodEvent).where(IfoodEvent.merchant_id == order.merchant_id,
                 IfoodEvent.order_id == order.external_id).order_by(IfoodEvent.created_at.desc())))
    alerts = []
    cancellation_requested = cancellation_pending(db, order)
    if cancellation_requested:
        alerts.append("Cancelamento solicitado no iFood; aguardando resultado")
    for event in events:
        if event.error:
            alerts.append(event.error)
    for event in events:
        if event.code not in STATES and event.code not in TRACKING and event.code not in (
                "CANCELLATION_REQUESTED", "CANCELLATION_REQUEST_FAILED"):
            alerts.append(f"Evento requer conferência no Gestor iFood: {event.code}")
    result = {"id": order.id, "origem": "ifood", "unidade_id": order.unidade_id,
              "nome": f"iFood #{order.display_id}", "estado_operacional": order.state,
              "total": str(order.total), "created_at": order.created_at, "synced_at": order.synced_at,
              "order_type": order.order_type, "delivered_by": order.delivered_by,
              "actions": ([] if pending or cancellation_requested or not settings.ifood_enabled
                          else allowed_actions(order)),
              "pending": command_dict(pending) if pending else None, "alerts": list(dict.fromkeys(alerts)),
              "preparation_start_at": order.payload.get("preparationStartDateTime"),
              "cancellation_requested": cancellation_requested,
              "confirmation_deadline": order.payload.get("confirmationDeadline") or (
                  utc(order.created_at) + timedelta(minutes=8) if order.state == "PLACED" else None)}
    if detail:
        result.update(payload=order.payload, commands=[command_dict(c) for c in commands],
                      events=[{"id": e.id, "code": e.code, "created_at": e.created_at,
                               "metadata": e.payload.get("metadata", {}), "error": e.error} for e in events])
    return result
