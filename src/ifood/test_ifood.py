"""Integração simulada: nenhum teste chama o iFood ou o banco configurado."""
from datetime import timedelta
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest
import requests
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.config import settings
from src.database import Base, get_db
from src.ifood.client import IfoodClient, IfoodError
from src.ifood.model import IfoodCommand, IfoodEvent, IfoodItem, IfoodOrder, now
from src.ifood.router import operator
from src.ifood.service import allowed_actions, enqueue, process_event, save_events, order_dict, utc
from src.ifood.worker import cycle, send_commands
from src.ifood import worker
from src.ifood import router as routes
from src.permissoes.model import Permissao, TipoPermissao
from src.usuarios.model import Usuario, FuncaoUsuario
from src.main import app
from src.pedidos.model import Pedido


@pytest.fixture(name="db")
def fixture_db(monkeypatch):
    monkeypatch.setattr(settings, "ifood_enabled", True)
    monkeypatch.setattr(settings, "ifood_test_merchants", {"test-store": 1})
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def event(code="PLACED", event_id="event-1", at=None):
    return {"id": event_id, "merchantId": "test-store", "orderId": "external-1", "fullCode": code,
            "code": code, "createdAt": (at or now()).isoformat()}


def api_mock():
    api = Mock()
    api.details.return_value = {"id": "external-1", "displayId": "1234", "merchant": {"id": "test-store"},
                                "orderType": "DELIVERY", "delivery": {"deliveredBy": "MERCHANT"},
                                "total": {"orderAmount": 39.90}, "items": [{"id": "unknown-product",
                                "name": "Dog de teste", "quantity": 2, "unitPrice": 19.95}]}
    api.polling.return_value = []
    return api


def imported(db, api=None):
    api = api or api_mock()
    save_events(db, [event()])
    process_event(db, db.get(IfoodEvent, "event-1"), api)
    return db.scalar(select(IfoodOrder)), api


def response(status=200, data=None):
    res = Mock(status_code=status, ok=status < 400, content=b"body", headers={})
    res.json.return_value = data
    return res


def test_token_cache_expires_in_and_401():
    session = Mock()
    clock = Mock(return_value=0)
    session.post.return_value = response(data={"accessToken": "a" * 8000, "expiresIn": 10})
    session.request.return_value = response(data={"ok": True})
    client = IfoodClient(session, clock)
    client.request("GET", "/test")
    clock.return_value = 9
    client.request("GET", "/test")
    assert session.post.call_count == 1
    clock.return_value = 10
    client.request("GET", "/test")
    assert session.post.call_count == 2
    session.request.side_effect = [response(401), response(data=[])]
    client.polling(["test-store"])
    assert session.post.call_count == 3
    assert session.request.call_args.kwargs["headers"]["x-polling-merchants"] == "test-store"


def test_401_is_bounded_and_secrets_not_in_error():
    session = Mock()
    session.post.return_value = response(data={"accessToken": "secret", "expiresIn": 50})
    session.request.return_value = response(401)
    with pytest.raises(IfoodError, match="HTTP 401"):
        IfoodClient(session).request("GET", "/test")
    assert session.request.call_count == 2


def test_dedup_snapshot_no_catalog_or_local_order(db):
    order, api = imported(db)
    save_events(db, [event()])
    assert len(list(db.scalars(select(IfoodEvent)))) == 1
    assert len(list(db.scalars(select(IfoodItem)))) == 1
    assert db.scalar(select(Pedido)) is None
    assert str(order.total) == "39.90"
    assert order.payload["items"][0]["id"] == "unknown-product"
    assert api.details.call_count == 1


def test_terminal_state_and_old_events(db):
    order, api = imported(db)
    timestamp = now()
    for code, i, at in [("CONCLUDED", "end", timestamp), ("PLACED", "late", timestamp - timedelta(minutes=1)),
                        ("CONFIRMED", "new-but-lower", timestamp + timedelta(seconds=1))]:
        save_events(db, [event(code, i, at)])
        process_event(db, db.get(IfoodEvent, i), api)
    assert order.state == "CONCLUDED"


def test_lifecycle_commands_and_cancellation(db):
    order, api = imported(db)
    for action, code in [("confirm", "CONFIRMED"), ("startPreparation", "PREPARATION_STARTED"),
                         ("readyToPickup", "READY_TO_PICKUP"), ("dispatch", "DISPATCHED"),
                         ("requestCancellation", "CANCELLED")]:
        payload = {"reason": "503"} if action == "requestCancellation" else {}
        command = enqueue(db, order.id, action, action, payload)
        assert enqueue(db, order.id, action, action, payload).id == command.id
        with pytest.raises(HTTPException) as exc:
            enqueue(db, order.id, action, "another", payload)
        assert exc.value.status_code == 409
        send_commands(db, api)
        assert command.state == "pending"
        assert order.state != code
        save_events(db, [event(code, action)])
        process_event(db, db.get(IfoodEvent, action), api)
        assert command.state == "confirmed"
        assert order.state == code


def test_dispatch_rules_scheduled_and_takeout(db):
    order, _ = imported(db)
    order.state = "READY_TO_PICKUP"
    assert "dispatch" in allowed_actions(order)
    order.delivered_by = "IFOOD"
    assert "dispatch" not in allowed_actions(order)
    order.delivered_by, order.order_type = "MERCHANT", "TAKEOUT"
    assert "dispatch" not in allowed_actions(order)
    order.state = "CONFIRMED"
    order.payload = {**order.payload, "preparationStartDateTime": (now() + timedelta(hours=1)).isoformat()}
    assert "startPreparation" not in allowed_actions(order)
    assert "readyToPickup" not in allowed_actions(order)


def test_indeterminate_not_resent_then_reconciled(db):
    order, api = imported(db)
    command = enqueue(db, order.id, "confirm", "lost-response", {})
    api.command.side_effect = requests.Timeout()
    send_commands(db, api)
    assert command.state == "indeterminate"
    send_commands(db, api)
    assert api.command.call_count == 1
    with pytest.raises(HTTPException):
        enqueue(db, order.id, "confirm", "new-key", {})
    save_events(db, [event("CONFIRMED", "reconcile")])
    process_event(db, db.get(IfoodEvent, "reconcile"), api)
    assert command.state == "confirmed"


def test_cancel_rejected_and_recovery_after_crash(db):
    order, api = imported(db)
    command = enqueue(db, order.id, "requestCancellation", "cancel", {"reason": "503"})
    command.state, command.sent_at = "sending", now()
    db.commit()
    send_commands(db, api)
    assert command.state == "indeterminate"
    api.command.assert_not_called()
    save_events(db, [event("CANCELLATION_REQUEST_FAILED", "rejection")])
    process_event(db, db.get(IfoodEvent, "rejection"), api)
    assert command.state == "rejected"
    assert order.state != "CANCELLED"


def test_durable_before_ack_and_restart(db):
    api = api_mock()
    api.polling.return_value = [event()]
    def failed_ack(_ids):
        assert db.get(IfoodEvent, "event-1") is not None
        raise IfoodError(503)
    api.acknowledge.side_effect = failed_ack
    with pytest.raises(IfoodError):
        cycle(db, api)
    assert not db.get(IfoodEvent, "event-1").processed
    api.acknowledge.side_effect = None
    api.polling.return_value = []
    cycle(db, api)
    assert db.get(IfoodEvent, "event-1").acknowledged
    assert db.get(IfoodEvent, "event-1").processed
    assert db.scalar(select(IfoodOrder)) is not None


def test_unknown_merchant_disabled_and_mismatched_details(db, monkeypatch):
    payload = event()
    payload["merchantId"] = "production-not-allowed"
    with pytest.raises(HTTPException):
        save_events(db, [payload])
    assert db.get(IfoodEvent, payload["id"]) is None
    monkeypatch.setattr(settings, "ifood_enabled", False)
    with pytest.raises(HTTPException):
        save_events(db, [event()])


def test_routes_scope_pagination_history_and_masked_credentials(db):
    order, _ = imported(db)
    actor = {"admin": False, "unit": 1, "perms": {"cozinha"}}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[operator] = lambda: actor
    try:
        with TestClient(app) as http:
            result = http.get("/pedidos/centralizados").json()
            assert result["total"] == 1
            assert result["items"][0]["origem"] == "ifood"
            assert http.get("/pedidos/centralizados?unidade_id=2").status_code == 403
            assert http.get(f"/integracoes/ifood/pedidos/{order.id}").status_code == 200
            assert "clientSecret" not in http.get("/pedidos/centralizados").text
            assert http.post(f"/integracoes/ifood/pedidos/{order.id}/acoes/confirm", json={},
                             headers={"Idempotency-Key": "test"}).status_code == 403
            actor["unit"] = 2
            assert http.get(f"/integracoes/ifood/pedidos/{order.id}").status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(operator, None)


def test_real_operator_requires_local_registration_and_permissions(db):
    with pytest.raises(HTTPException) as exc:
        operator({"sub": "unknown-user"}, db)
    assert exc.value.status_code == 403


def test_unknown_event_and_snapshot_merchant_check(db):
    order, api = imported(db)
    save_events(db, [event("HANDSHAKE_DISPUTE", "dispute")])
    process_event(db, db.get(IfoodEvent, "dispute"), api)
    assert "HANDSHAKE_DISPUTE" in order_dict(db, order)["alerts"][0]
    assert order_dict(db, order)["confirmation_deadline"] is not None
    payload = event("PLACED", "another")
    payload["orderId"] = "different-order"
    save_events(db, [payload])
    api.details.return_value["merchant"]["id"] = "wrong-store"
    with pytest.raises(ValueError):
        process_event(db, db.get(IfoodEvent, "another"), api)
    db.rollback()
    assert len(list(db.scalars(select(IfoodOrder)))) == 1


def test_ifood_delivery_updates_from_events_and_failed_details_retry(db):
    api = api_mock()
    api.polling.return_value = [event("READY_TO_PICKUP", "ready")]
    api.details.side_effect = requests.Timeout()
    cycle(db, api)
    ready = db.get(IfoodEvent, "ready")
    assert not ready.processed
    assert ready.acknowledged
    assert ready.next_attempt_at is not None
    ready.next_attempt_at = now() - timedelta(seconds=1)
    db.commit()
    api.details.side_effect = None
    api.details.return_value["delivery"]["deliveredBy"] = "IFOOD"
    api.polling.return_value = []
    cycle(db, api)
    order = db.scalar(select(IfoodOrder))
    assert "dispatch" not in allowed_actions(order)
    api.polling.return_value = [event("DISPATCHED", "out")]
    cycle(db, api)
    assert order.state == "DISPATCHED"


def test_details_404_retries_with_backoff_then_abandons(db, central_http, monkeypatch):
    http, _actor = central_http
    clock = {"at": now()}
    monkeypatch.setattr(worker, "now", lambda: clock["at"])
    api = api_mock()
    api.polling.return_value = [event()]
    api.details.side_effect = IfoodError(404)
    cycle(db, api)
    api.polling.return_value = []
    failed = db.get(IfoodEvent, "event-1")
    assert failed.attempts == 1 and not failed.processed
    cycle(db, api)
    assert api.details.call_count == 1, "backoff must skip the event until next_attempt_at"
    for _ in range(40):
        clock["at"] += timedelta(seconds=30)
        cycle(db, api)
    assert failed.processed and "10 minutos" in failed.error
    # 30s, 60s, 120s, 240s, then the deadline: bounded, never one call per cycle.
    assert api.details.call_count <= 7
    assert db.scalar(select(IfoodOrder)) is None
    assert http.get("/pedidos/centralizados").json()["integration"]["abandoned_events"] == 1


def test_failing_order_does_not_block_others_or_commands(db):
    order, api = imported(db)
    command = enqueue(db, order.id, "confirm", "confirm-while-other-fails", {})
    broken, healthy = event("PLACED", "broken"), event("PLACED", "healthy")
    broken["orderId"], healthy["orderId"] = "missing-order", "another-order"
    api.polling.return_value = [broken, healthy]
    healthy_details = api.details.return_value
    def details(order_id):
        if order_id == "missing-order":
            raise IfoodError(404)
        return healthy_details
    api.details.side_effect = details
    cycle(db, api)
    assert not db.get(IfoodEvent, "broken").processed
    assert db.get(IfoodEvent, "healthy").processed
    assert len(list(db.scalars(select(IfoodOrder)))) == 2
    api.command.assert_called_once()
    assert command.state != "queued"


def test_rate_limited_details_stop_imports_but_send_commands(db):
    order, api = imported(db)
    enqueue(db, order.id, "confirm", "confirm-under-429", {})
    first, second = event("PLACED", "first"), event("PLACED", "second")
    first["orderId"], second["orderId"] = "order-a", "order-b"
    api.polling.return_value = [first, second]
    api.details.reset_mock()
    api.details.side_effect = IfoodError(429, retry_after=120)
    cycle(db, api)
    assert api.details.call_count == 1
    deferred = db.get(IfoodEvent, "first")
    assert utc(deferred.next_attempt_at) - now() > timedelta(seconds=100)
    api.command.assert_called_once()


def test_rate_limited_command_waits_for_retry_cycle(db):
    order, api = imported(db)
    command = enqueue(db, order.id, "confirm", "rate-limit", {})
    api.command.side_effect = IfoodError(429, retry_after=120)
    with pytest.raises(IfoodError) as exc:
        send_commands(db, api)
    assert exc.value.retry_after == 120
    assert command.state == "queued"
    assert command.sent_at is None


def test_registered_operator_permissions(db):
    permission = Permissao(nome=TipoPermissao.cozinha)
    user = Usuario(nome="Cozinha", email="cook@example.test", auth_provider_id="cook", unidade_id=1,
                   funcao=FuncaoUsuario.cozinha, permissoes=[permission])
    db.add(user)
    db.commit()
    actor = operator({"sub": "cook"}, db)
    assert actor == {"admin": False, "unit": 1, "perms": {"cozinha"}}
    user.permissoes = []
    db.commit()
    with pytest.raises(HTTPException):
        operator({"sub": "cook"}, db)


def test_cancellation_policy_and_idempotency_route(db, monkeypatch):
    order, _ = imported(db)
    monkeypatch.setattr(routes.client, "reasons", lambda _id: {"reasons": [{"code": "503", "description": "Sem item"}]})
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[operator] = lambda: {"admin": True, "unit": None, "perms": set()}
    try:
        with TestClient(app) as http:
            path = f"/integracoes/ifood/pedidos/{order.id}/acoes/requestCancellation"
            assert http.post(path, json={"reason": "999"}, headers={"Idempotency-Key": "bad"}).status_code == 422
            first = http.post(path, json={"reason": "503"}, headers={"Idempotency-Key": "good"})
            assert first.status_code == 202
            again = http.post(path, json={"reason": "503"}, headers={"Idempotency-Key": "good"})
            assert again.json()["id"] == first.json()["id"]
            assert len(list(db.scalars(select(IfoodCommand)))) == 1
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(operator, None)



def test_external_cancellation_blocks_actions_until_rejected(db):
    order, api = imported(db)
    save_events(db, [event("CANCELLATION_REQUESTED", "external-cancel")])
    process_event(db, db.get(IfoodEvent, "external-cancel"), api)
    assert order_dict(db, order)["actions"] == []
    with pytest.raises(HTTPException):
        enqueue(db, order.id, "confirm", "wait-for-cancel", {})
    save_events(db, [event("CANCELLATION_REQUEST_FAILED", "external-cancel-rejected")])
    process_event(db, db.get(IfoodEvent, "external-cancel-rejected"), api)
    assert "confirm" in order_dict(db, order)["actions"]


def test_first_tracking_event_does_not_assume_placed(db):
    api = api_mock()
    save_events(db, [event("ASSIGN_DRIVER", "tracking-first")])
    process_event(db, db.get(IfoodEvent, "tracking-first"), api)
    order = db.scalar(select(IfoodOrder))
    assert order.state == "UNKNOWN"
    assert allowed_actions(order) == []



def test_standalone_worker_registers_foreign_key_models():
    """A fresh interpreter must flush an imported order without importing src.main."""
    script = """
from datetime import time
from src.ifood import worker
from src.ifood.model import IfoodOrder
from src.database import Base, engine, SessionLocal
import sys
assert 'src.main' not in sys.modules
Base.metadata.create_all(engine)
from src.unidades.model import Unidade
with SessionLocal() as db:
    db.add(Unidade(id=1, nome='Unidade teste', abertura=time(10), fechamento=time(23)))
    db.flush()
    db.add(IfoodOrder(merchant_id='test-store', external_id='order-test',
                      unidade_id=1, display_id='123', state='PLACED'))
    db.flush()
    db.commit()
"""
    # Never inherit the developer's real database in this regression test.
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "DATABASE_URL": "sqlite:///:memory:"},
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture(name="central_http")
def fixture_central_http(db):
    app.dependency_overrides[get_db] = lambda: db
    actor = {"admin": True, "unit": None, "perms": set()}
    app.dependency_overrides[operator] = lambda: actor
    with TestClient(app) as http:
        yield http, actor
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(operator, None)


def test_search_finds_ifood_order_outside_first_page(db, central_http):
    http, _actor = central_http
    for i in range(35):
        db.add(IfoodOrder(merchant_id="test-store", external_id=f"external-{i}", unidade_id=1,
                          display_id=f"{1000 + i}", state="CONFIRMED",
                          created_at=now() - timedelta(minutes=35 - i),
                          payload={"customer": {"name": "Pessoa exclusiva" if i == 0 else "Cliente comum"}}))
    db.commit()
    first = http.get("/pedidos/centralizados?origem=ifood").json()
    assert first["total"] == 35
    assert not any(item["nome"] == "iFood #1000" for item in first["items"])
    for query in ("Pessoa exclusiva", "external-0", "1000", "#1000"):
        result = http.get("/pedidos/centralizados", params={"origem": "ifood", "busca": query}).json()
        assert result["total"] == 1
        assert result["items"][0]["nome"] == "iFood #1000"


def test_search_restaurant_customer_and_literal_wildcards(db, central_http):
    from src.clientes.model import Cliente  # pylint: disable=import-outside-toplevel
    http, _actor = central_http
    customer = Cliente(nome="Cliente especial", telefone="61999990000")
    db.add(customer)
    db.flush()
    own = Pedido(unidade_id=1, nome_comanda="Mesa 100%_VIP", cliente_id=customer.id)
    db.add(own)
    db.commit()
    for term in ("100%_VIP", "cliente especial", str(own.id)):
        result = http.get("/pedidos/centralizados", params={"origem": "proprio", "busca": term}).json()
        assert result["total"] == 1
        assert result["items"][0]["origem"] == "proprio"
    assert http.get("/pedidos/centralizados", params={"busca": "missing"}).json()["total"] == 0
    # % is literal, so it must not match a plain iFood display id.
    imported(db)
    assert http.get("/pedidos/centralizados", params={"origem": "ifood", "busca": "%"}).json()["total"] == 0


def test_kitchen_views_include_new_ready_and_cancelled_orders(db, central_http):
    http, _actor = central_http
    states = ("PLACED", "CONFIRMED", "PREPARATION_STARTED", "READY_TO_PICKUP",
              "DISPATCHED", "CONCLUDED", "CANCELLED")
    for i, state in enumerate(states):
        db.add(IfoodOrder(merchant_id="test-store", external_id=f"kitchen-{i}", unidade_id=1,
                          display_id=str(i), state=state, payload={"items": [{"name": "Dog", "quantity": 1}]}))
    db.commit()
    for view, expected in (("fila", {"PLACED", "CONFIRMED", "PREPARATION_STARTED"}),
                           ("prontos", {"READY_TO_PICKUP", "DISPATCHED", "CONCLUDED"}),
                           ("cancelados", {"CANCELLED"})):
        data = http.get("/pedidos/centralizados", params={"cozinha": "true", "cozinha_visao": view}).json()
        assert {order["estado_operacional"] for order in data["items"]} == expected
        assert all("payload" in order for order in data["items"])


def test_local_details_and_search_enforce_unit_scope(db, central_http):
    http, actor = central_http
    own = Pedido(unidade_id=1, nome_comanda="Mesa reservada")
    db.add(own)
    db.commit()
    path = f"/pedidos/centralizados/proprio/{own.id}"
    assert http.get(path).json()["nome"] == "Mesa reservada"
    actor.update(admin=False, unit=2, perms={"cozinha"})
    assert http.get(path).status_code == 403
    assert http.get("/pedidos/centralizados", params={"busca": "reservada"}).json()["total"] == 0
