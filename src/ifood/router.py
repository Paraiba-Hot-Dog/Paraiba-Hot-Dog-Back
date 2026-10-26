"""Consultas unificadas e comandos autenticados do ambiente de testes."""
import threading
import time
from decimal import Decimal
from typing import Literal

import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import String, case, cast, exists, func, literal, select, union_all
from sqlalchemy.orm import Session, selectinload

from src.clientes.model import Cliente
from src.config import settings
from src.database import get_db
from src.ifood.client import IfoodError, client
from src.ifood.model import IfoodCommand, IfoodEvent, IfoodHealth, IfoodOrder
from src.ifood.service import (command_dict, enqueue, guard_merchant, open_dispute, order_dict, pickup_code,
                               utc)
from src.pedidos.model import ItemPedido, Pedido
from src.pedidos.schema import PedidoRead
from src.security import get_current_user
from src.usuarios.model import Usuario

router = APIRouter()
Action = Literal["confirm", "startPreparation", "readyToPickup", "dispatch", "requestCancellation"]


def operator(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.get("sub"):
        raise HTTPException(403, "Usuário sem identificador")
    usuario = db.scalar(select(Usuario).options(selectinload(Usuario.permissoes))
                        .where(Usuario.auth_provider_id == user.get("sub")))
    if not usuario:
        raise HTTPException(403, "Usuário não cadastrado")
    perms = {p.nome.value for p in usuario.permissoes}
    admin = usuario.funcao.value == "administrador"
    if not admin and (not usuario.unidade_id or not perms.intersection({"anotar_pedidos", "cozinha"})):
        raise HTTPException(403, "Sem permissão para acompanhar pedidos")
    return {"admin": admin, "unit": usuario.unidade_id, "perms": perms}


def unit_scope(actor, requested):
    if not actor["admin"]:
        if requested is not None and requested != actor["unit"]:
            raise HTTPException(403, "Unidade não autorizada")
        return actor["unit"]
    return requested


def get_order(db, order_id, actor):
    order = db.get(IfoodOrder, order_id)
    if not order:
        raise HTTPException(404, "Pedido não encontrado")
    unit_scope(actor, order.unidade_id)
    if settings.ifood_test_merchants.get(order.merchant_id) != order.unidade_id:
        raise HTTPException(403, "Merchant fora da configuração de testes")
    return order


def external_call(callback):
    try:
        return callback()
    except (IfoodError, requests.RequestException, ValueError) as exc:
        raise HTTPException(502, "Não foi possível consultar o iFood. Tente novamente mais tarde.") from exc


class CentralFilters(BaseModel):
    unidade_id: int | None = Field(None, gt=0)
    origem: Literal["proprio", "ifood"] | None = None
    estado_operacional: str | None = None
    cozinha: bool = False
    cozinha_visao: Literal["fila", "prontos", "cancelados"] = "fila"
    busca: str = Field("", max_length=120)
    skip: int = Field(0, ge=0)
    limit: int = Field(30, ge=1, le=100)


def centralized_query(filters, unit):
    def item_exists(state):
        return exists(select(ItemPedido.id).where(
            ItemPedido.pedido_id == Pedido.id, ItemPedido.status == state))
    local_state = case((Pedido.status == "cancelado", "CANCELLED"),
                       (item_exists("preparando"), "PREPARATION_STARTED"),
                       (item_exists("aberto"), "PLACED"), else_="CONCLUDED")
    customer_name = select(Cliente.nome).where(Cliente.id == Pedido.cliente_id).scalar_subquery()
    own_search = (cast(Pedido.id, String) + " " + Pedido.nome_comanda + " "
                  + func.coalesce(customer_name, ""))
    ext_search = (IfoodOrder.display_id + " " + IfoodOrder.external_id + " "
                  + func.coalesce(IfoodOrder.payload["customer"]["name"].as_string(), ""))
    own = select(own_search.label("search"), Pedido.id.label("id"), literal("proprio").label("origem"),
                 Pedido.unidade_id.label("unit"), local_state.label("state"), Pedido.created_at.label("created_at"))
    ext = select(ext_search.label("search"), IfoodOrder.id.label("id"), literal("ifood").label("origem"),
                 IfoodOrder.unidade_id.label("unit"), IfoodOrder.state.label("state"),
                 IfoodOrder.created_at.label("created_at"))
    ext = ext.where(IfoodOrder.merchant_id.in_(list(settings.ifood_test_merchants)))
    if filters.origem == "ifood" or filters.cozinha:
        own = own.where(literal(False))
    if filters.origem == "proprio":
        ext = ext.where(literal(False))
    rows = union_all(own, ext).subquery()
    query = select(rows)
    if unit is not None:
        query = query.where(rows.c.unit == unit)
    if filters.estado_operacional:
        query = query.where(rows.c.state == filters.estado_operacional)
    if filters.busca.strip():
        search = filters.busca.strip()
        if search.startswith("#") and search[1:].isdigit():
            search = search[1:]
        term = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(rows.c.search.ilike(f"%{term}%", escape="\\"))
    if filters.cozinha:
        kitchen_states = {
            "fila": ("UNKNOWN", "PLACED", "CONFIRMED", "PREPARATION_STARTED"),
            "prontos": ("READY_TO_PICKUP", "DISPATCHED", "CONCLUDED"),
            "cancelados": ("CANCELLED",),
        }
        query = query.where(rows.c.state.in_(kitchen_states[filters.cozinha_visao]))
    return query, rows


@router.get("/pedidos/centralizados")
def centralized(filters: CentralFilters = Depends(), actor=Depends(operator), db: Session = Depends(get_db)):
    unit = unit_scope(actor, filters.unidade_id)
    query, rows = centralized_query(filters, unit)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    page = db.execute(query.order_by(rows.c.created_at.desc(), rows.c.origem, rows.c.id.desc())
                      .offset(filters.skip).limit(filters.limit)).mappings()
    result = []
    for row in page:
        if row["origem"] == "ifood":
            result.append(order_dict(db, db.get(IfoodOrder, row["id"]), detail=filters.cozinha))
        else:
            order = db.get(Pedido, row["id"])
            result.append(local_order_dict(order))
    health = db.get(IfoodHealth, 1)
    abandoned = select(func.count()).where(
        IfoodEvent.processed.is_(True), IfoodEvent.error.is_not(None),
        IfoodEvent.merchant_id.in_([m for m, u in settings.ifood_test_merchants.items()
                                    if unit is None or u == unit]))
    return {"items": result, "total": total, "skip": filters.skip, "limit": filters.limit,
            "integration": {"enabled": settings.ifood_enabled, "environment": "test",
                            "last_poll_at": health.last_poll_at if health else None,
                            "error": health.error if health else None,
                            "abandoned_events": db.scalar(abandoned)}}


def local_order_dict(order):
    items = [item for item in order.itens if item.status.value != "cancelado"]
    state = ("CANCELLED" if order.status.value == "cancelado" else
             "PREPARATION_STARTED" if any(item.status.value == "preparando" for item in items) else
             "PLACED" if any(item.status.value == "aberto" for item in items) else "CONCLUDED")
    payload = PedidoRead.model_validate(order).model_dump(mode="json")
    if order.cliente:
        payload["customer"] = {"name": order.cliente.nome, "phone": {"number": order.cliente.telefone}}
    return {"id": order.id, "origem": "proprio", "unidade_id": order.unidade_id,
            "nome": order.nome_comanda, "estado_operacional": state,
            "total": str(order.total), "created_at": utc(order.created_at),
            "synced_at": None, "actions": [], "pending": None, "alerts": [], "payload": payload}


@router.get("/pedidos/centralizados/proprio/{order_id}")
def local_detail(order_id: int, actor=Depends(operator), db: Session = Depends(get_db)):
    order = db.get(Pedido, order_id)
    if not order:
        raise HTTPException(404, "Pedido não encontrado")
    unit_scope(actor, order.unidade_id)
    return local_order_dict(order)


@router.get("/integracoes/ifood/pedidos/{order_id}")
def detail(order_id: int, actor=Depends(operator), db: Session = Depends(get_db)):
    return order_dict(db, get_order(db, order_id, actor), detail=True)


@router.get("/integracoes/ifood/pedidos/{order_id}/motivos-cancelamento")
def reasons(order_id: int, actor=Depends(operator), db: Session = Depends(get_db)):
    order = get_order(db, order_id, actor)
    guard_merchant(order.merchant_id)
    if not actor["admin"] and "anotar_pedidos" not in actor["perms"]:
        raise HTTPException(403, "Sem permissão para cancelar pedidos")
    return external_call(lambda: client.reasons(order.external_id))


class CommandInput(BaseModel):
    reason: str | None = Field(None, min_length=1, max_length=100)


@router.post("/integracoes/ifood/pedidos/{order_id}/acoes/{action}", status_code=202)
def execute(
    *, order_id: int, action: Action,
    data: CommandInput,
    idempotency_key: str = Header(..., min_length=1, max_length=100),
    actor=Depends(operator), db: Session = Depends(get_db),
):
    order = get_order(db, order_id, actor)
    guard_merchant(order.merchant_id)
    kitchen_action = action in ("startPreparation", "readyToPickup")
    if not actor["admin"] and "anotar_pedidos" not in actor["perms"] and not kitchen_action:
        raise HTTPException(403, "Sem permissão para esta ação")
    payload = {"deliveredBy": "MERCHANT"} if action == "dispatch" else {}
    # Idempotent replay must not depend on today's cancellation policy.
    existing = db.scalar(select(IfoodCommand).where(IfoodCommand.order_id == order_id,
                                                    IfoodCommand.request_key == idempotency_key))
    if action == "requestCancellation":
        if not data.reason:
            raise HTTPException(422, "Selecione um motivo de cancelamento")
        payload = {"reason": data.reason}
        if not existing:
            available = external_call(lambda: client.reasons(order.external_id))
            available = available.get("reasons", []) if isinstance(available, dict) else available
            if data.reason not in {str(r["code"]) for r in (available or [])}:
                raise HTTPException(422, "Motivo não disponível para este pedido")
    return command_dict(enqueue(db, order_id, action, idempotency_key, payload))


class DisputeInput(BaseModel):
    reason: str | None = Field(None, min_length=1, max_length=250)
    alternative_id: str | None = Field(None, min_length=1, max_length=100)
    amount: str | None = Field(None, pattern=r"^\d+(\.\d{1,2})?$")
    minutes: int | None = Field(None, gt=0)


def dispute_payload(dispute, action, data):
    """Validate the reply against the options offered in the HANDSHAKE_DISPUTE event."""
    nested = dispute.get("metadata") or {}
    if action == "accept":
        reasons = nested.get("acceptCancellationReasons") or []
        if reasons and data.reason not in reasons:
            raise HTTPException(422, "Selecione um motivo para aceitar")
        return "accept", {"reason": data.reason} if reasons else None
    if action == "reject":
        if not data.reason:
            raise HTTPException(422, "Informe o motivo da recusa")
        return "reject", {"reason": data.reason}
    alternative = next((a for a in dispute.get("alternatives") or [] if a.get("id") == data.alternative_id), None)
    if not alternative:
        raise HTTPException(422, "Contraproposta não oferecida nesta negociação")
    meta = alternative.get("metadata") or {}
    if alternative.get("type") == "REFUND":
        limit = (meta.get("maxAmount") or {})
        if not data.amount or Decimal(data.amount) <= 0 or Decimal(data.amount) > Decimal(str(limit.get("value", 0))):
            raise HTTPException(422, "Valor de reembolso fora do limite permitido")
        body = {"type": "REFUND", "metadata": {"amount": {
            "currency": limit.get("currency", "BRL"), "value": data.amount}}}
    elif alternative.get("type") == "ADDITIONAL_TIME":
        if (data.minutes not in (meta.get("allowedsAdditionalTimeInMinutes") or [])
                or data.reason not in (meta.get("allowedsAdditionalTimeReasons") or [])):
            raise HTTPException(422, "Tempo adicional ou motivo não permitido")
        body = {"type": "ADDITIONAL_TIME", "metadata": {
            "additionalTimeInMinutes": data.minutes, "additionalTimeReason": data.reason}}
    else:
        raise HTTPException(422, "Tipo de contraproposta não suportado; responda no Gestor iFood")
    return f"alternatives/{alternative['id']}", body


@router.post("/integracoes/ifood/pedidos/{order_id}/disputas/{dispute_id}/{action}", status_code=202)
def answer_dispute(
    *, order_id: int, dispute_id: str, action: Literal["accept", "reject", "alternative"],
    data: DisputeInput,
    idempotency_key: str = Header(..., min_length=1, max_length=100),
    actor=Depends(operator), db: Session = Depends(get_db),
):
    order = get_order(db, order_id, actor)
    guard_merchant(order.merchant_id)
    if not actor["admin"] and "anotar_pedidos" not in actor["perms"]:
        raise HTTPException(403, "Sem permissão para responder negociações")
    name = {"accept": "disputeAccept", "reject": "disputeReject", "alternative": "disputeAlternative"}[action]
    existing = db.scalar(select(IfoodCommand).where(IfoodCommand.order_id == order_id,
                                                    IfoodCommand.request_key == idempotency_key))
    if existing:
        return command_dict(existing)
    dispute = open_dispute(db, order)
    if not dispute or dispute["disputeId"] != dispute_id:
        raise HTTPException(409, "Negociação encerrada ou expirada")
    path, body = dispute_payload(dispute, action, data)
    return command_dict(enqueue(db, order_id, name, idempotency_key,
                                {"disputeId": dispute_id, "path": path, "body": body}))


class PickupInput(BaseModel):
    code: str = Field(..., pattern=r"^[0-9A-Za-z]{1,20}$")


@router.post("/integracoes/ifood/pedidos/{order_id}/validar-coleta")
def validate_pickup(order_id: int, data: PickupInput, actor=Depends(operator), db: Session = Depends(get_db)):
    order = get_order(db, order_id, actor)
    guard_merchant(order.merchant_id)
    if pickup_code(order) is None:
        raise HTTPException(409, "Validação de coleta só se aplica a entrega iFood antes da saída do pedido")
    try:
        result = client.validate_pickup_code(order.external_id, data.code)
    except IfoodError as exc:
        if 400 <= exc.status < 500 and exc.status not in (401, 408, 429):
            raise HTTPException(409, "O iFood não aceitou a validação; confira o código ou o Gestor iFood") from exc
        raise HTTPException(502, "Não foi possível consultar o iFood. Tente novamente mais tarde.") from exc
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(502, "Não foi possível consultar o iFood. Tente novamente mais tarde.") from exc
    return {"valid": bool((result or {}).get("valid"))}


# Endpoint guide: at most one tracking request every 30 seconds per order.
TRACKING_INTERVAL = 30
_tracking_cache: dict[int, tuple[float, dict]] = {}
_tracking_lock = threading.Lock()


@router.get("/integracoes/ifood/pedidos/{order_id}/rastreamento")
def tracking(order_id: int, actor=Depends(operator), db: Session = Depends(get_db)):
    order = get_order(db, order_id, actor)
    guard_merchant(order.merchant_id)
    assigned = db.scalar(select(exists().where(
        IfoodEvent.merchant_id == order.merchant_id, IfoodEvent.order_id == order.external_id,
        IfoodEvent.code == "ASSIGN_DRIVER")))
    if (order.order_type != "DELIVERY" or order.delivered_by != "IFOOD" or not assigned
            or order.state in ("CONCLUDED", "CANCELLED")):
        return {"available": False}
    with _tracking_lock:
        cached = _tracking_cache.get(order_id)
        if cached and time.monotonic() - cached[0] < TRACKING_INTERVAL:
            return cached[1]
        # Reserve the slot before the network call so concurrent viewers reuse the last answer.
        _tracking_cache[order_id] = (time.monotonic(), cached[1] if cached else {"available": False})
    try:
        raw = client.tracking(order.external_id) or {}
        result = {"available": True, **{k: raw.get(k) for k in (
            "latitude", "longitude", "expectedDelivery", "pickupEtaStart", "deliveryEtaEnd", "trackDate")}}
    except IfoodError as exc:
        if exc.status != 404:
            raise HTTPException(502, "Não foi possível consultar o iFood. Tente novamente mais tarde.") from exc
        result = {"available": False}
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(502, "Não foi possível consultar o iFood. Tente novamente mais tarde.") from exc
    with _tracking_lock:
        _tracking_cache[order_id] = (time.monotonic(), result)
    return result


@router.get("/integracoes/ifood/comandos/{command_id}")
def command_status(command_id: int, actor=Depends(operator), db: Session = Depends(get_db)):
    command = db.get(IfoodCommand, command_id)
    if not command:
        raise HTTPException(404, "Comando não encontrado")
    get_order(db, command.order_id, actor)
    return command_dict(command)
