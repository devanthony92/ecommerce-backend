"""Mercado Pago Checkout Pro.

Flujo: el pedido nace en PENDING_PAYMENT → se crea una preferencia y el cliente
paga en el sitio de Mercado Pago (`init_point`) → Mercado Pago avisa al webhook
→ se consulta el pago y, si está aprobado y el monto coincide, el pedido pasa a
PAID. El parámetro `?status=` con el que vuelve el cliente solo ajusta el mensaje.

Docs: https://www.mercadopago.com.co/developers/es/docs/checkout-pro
"""

import hashlib
import hmac
import uuid
from typing import Any

import httpx

from app.config import get_settings
from app.models import Order

API_URL = "https://api.mercadopago.com"
TIMEOUT = httpx.Timeout(10.0)


class PaymentGatewayError(Exception):
    pass


def _headers(**extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().mp_access_token}", **extra}


def confirmation_url(order: Order) -> str:
    return f"{get_settings().frontend_url}/checkout/confirmacion/{order.id}"


def create_preference(order: Order) -> str:
    """Crea la preferencia de pago y devuelve la URL a la que se redirige al cliente."""
    settings = get_settings()
    items: list[dict[str, Any]] = [
        {
            "id": item.variant_id,
            "title": f"{item.name} ({item.attributes['color']} / {item.attributes['size']})",
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "currency_id": "COP",
        }
        for item in order.items
    ]
    if order.shipping_cost:
        items.append(
            {
                "id": "shipping",
                "title": order.shipping["label"],
                "quantity": 1,
                "unit_price": order.shipping_cost,
                "currency_id": "COP",
            }
        )

    back_url = confirmation_url(order)
    body: dict[str, Any] = {
        "items": items,
        "external_reference": str(order.id),
        "back_urls": {"success": back_url, "pending": back_url, "failure": back_url},
        "statement_descriptor": "TRAMA",
    }
    # Mercado Pago solo acepta retorno automático y webhook hacia URLs públicas https.
    if back_url.startswith("https://"):
        body["auto_return"] = "approved"
    if settings.api_url.startswith("https://"):
        body["notification_url"] = f"{settings.api_url}/payments/mercadopago/webhook"

    try:
        response = httpx.post(
            f"{API_URL}/checkout/preferences",
            json=body,
            headers=_headers(**{"X-Idempotency-Key": str(uuid.uuid4())}),
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PaymentGatewayError("No se pudo crear la preferencia de pago.") from exc
    return response.json()["init_point"]


def get_payment(payment_id: str) -> dict[str, Any]:
    try:
        response = httpx.get(
            f"{API_URL}/v1/payments/{payment_id}", headers=_headers(), timeout=TIMEOUT
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise PaymentGatewayError("No se pudo consultar el pago.") from exc
    return response.json()


def valid_signature(signature: str | None, request_id: str | None, data_id: str) -> bool:
    """Comprueba el encabezado `x-signature` (HMAC-SHA256 con la clave del webhook)."""
    secret = get_settings().mp_webhook_secret
    if not secret or not signature:
        return False
    parts = dict(part.strip().split("=", 1) for part in signature.split(",") if "=" in part)
    ts, received = parts.get("ts"), parts.get("v1")
    if not ts or not received:
        return False
    manifest = f"id:{data_id.lower()};"
    if request_id:
        manifest += f"request-id:{request_id};"
    manifest += f"ts:{ts};"
    expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)
