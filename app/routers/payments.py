import contextlib
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request
from sqlalchemy import select

from app.dependencies import DbSession
from app.errors import AppError
from app.logging_config import error_logger
from app.models import Order
from app.services import mercadopago

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post("/mercadopago/webhook")
async def mercadopago_webhook(
    request: Request,
    db: DbSession,
    data_id: Annotated[str | None, Query(alias="data.id")] = None,
    topic: Annotated[str | None, Query(alias="type")] = None,
    x_signature: Annotated[str | None, Header()] = None,
    x_request_id: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Aviso de Mercado Pago. Nunca se confía en el contenido del aviso: se
    verifica la firma y luego se consulta el pago directamente a Mercado Pago."""
    body: dict[str, Any] = {}
    with contextlib.suppress(ValueError):
        body = await request.json()
    if not isinstance(body, dict):
        body = {}
    payment_id = data_id or str((body.get("data") or {}).get("id") or "")
    kind = topic or body.get("type")

    if not payment_id or not mercadopago.valid_signature(x_signature, x_request_id, payment_id):
        raise AppError(401, "INVALID_SIGNATURE", "Firma del aviso no válida.")
    # Otros avisos (reembolsos, contracargos…) se aceptan para que no se reintenten.
    if kind != "payment":
        return {"received": True}

    try:
        payment = mercadopago.get_payment(payment_id)
    except mercadopago.PaymentGatewayError as exc:
        # 502: Mercado Pago reintentará el aviso más tarde.
        raise AppError(502, "PAYMENT_GATEWAY_ERROR", "No se pudo consultar el pago.") from exc

    reference = str(payment.get("external_reference") or "")
    order = (
        db.scalar(select(Order).where(Order.id == int(reference)).with_for_update())
        if reference.isdigit()
        else None
    )
    if order is None:
        return {"received": True}

    approved = payment.get("status") == "approved"
    if approved and order.status == "PENDING_PAYMENT":
        if round(float(payment.get("transaction_amount", 0))) != order.total:
            # Monto distinto al del pedido: no se aprueba y queda registrado para revisarlo.
            error_logger.error(
                "Monto de pago distinto al del pedido",
                extra={"data": {"order": order.id, "payment": payment_id}},
            )
            return {"received": True}
        order.status = "PAID"
        order.payment_reference = payment_id
        db.commit()
    return {"received": True}
