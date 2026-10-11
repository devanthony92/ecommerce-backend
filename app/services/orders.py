"""Checkout y pedidos: opciones de envío, creación con descuento de stock y pago."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import (
    CANCELLABLE_STATUSES,
    EXPRESS_CITIES,
    EXPRESS_COST,
    FREE_SHIPPING_THRESHOLD,
    PAYMENT_METHODS,
    PICKUP_ADDRESS,
    SHIPPING_COST,
)
from app.errors import AppError
from app.models import Address, Order, ProductVariant
from app.services import mercadopago
from app.utils.money import format_cop

Json = dict[str, Any]


def shipping_options(cart: Json, address: Address) -> list[Json]:
    """Opciones y total por opción: los calcula el backend, el frontend solo los muestra."""
    items_total = cart["summary"]["total"] - cart["summary"]["shipping"]
    free_standard = items_total >= FREE_SHIPPING_THRESHOLD
    options = [
        {
            "id": "standard",
            "label": "Envío estándar",
            "description": f"Gratis por compras desde {format_cop(FREE_SHIPPING_THRESHOLD)}"
            if free_standard
            else "Transportadora nacional",
            "price": 0 if free_standard else SHIPPING_COST,
            "estimatedDays": "3 a 5 días hábiles",
        }
    ]
    if address.city in EXPRESS_CITIES:
        options.append(
            {
                "id": "express",
                "label": "Envío express",
                "description": "Para ciudades principales",
                "price": EXPRESS_COST,
                "estimatedDays": "1 a 2 días hábiles",
            }
        )
    options.append(
        {
            "id": "pickup",
            "label": "Recoger en bodega",
            "description": PICKUP_ADDRESS,
            "price": 0,
            "estimatedDays": "Listo en 1 día hábil",
        }
    )
    return [{**option, "total": items_total + option["price"]} for option in options]


def order_json(order: Order) -> Json:
    data: Json = {
        "id": order.id,
        "number": order.number,
        "createdAt": order.created_at.isoformat().replace("+00:00", "Z"),
        "status": order.status,
        "items": [
            {
                "productId": item.product_id,
                "productSlug": item.product_slug,
                "name": item.name,
                "image": item.image,
                "variant": {"id": item.variant_id, "attributes": item.attributes},
                "quantity": item.quantity,
                "unitPrice": item.unit_price,
                "lineTotal": item.line_total,
            }
            for item in order.items
        ],
        "summary": {
            "itemsCount": order.items_count,
            "subtotal": order.subtotal,
            "discountTotal": order.discount_total,
            "shipping": order.shipping_cost,
            "total": order.total,
        },
        "address": order.address,
        "shipping": order.shipping,
        "payment": {
            "method": order.payment_method,
            "label": PAYMENT_METHODS[order.payment_method]["label"],
        },
        "notes": order.notes,
        "canCancel": order.status in CANCELLABLE_STATUSES,
        "canReorder": True,
    }
    if order.status == "CANCELLED":
        data["cancelledAt"] = (
            order.cancelled_at.isoformat().replace("+00:00", "Z") if order.cancelled_at else None
        )
        data["cancelReason"] = order.cancel_reason
    return data


def reserve_stock(db: Session, quantities: dict[str, int]) -> None:
    """Descuenta stock bloqueando las filas: dos compras simultáneas no pueden
    llevarse las mismas unidades."""
    variants = db.scalars(
        select(ProductVariant)
        .where(ProductVariant.id.in_(quantities))
        .order_by(ProductVariant.id)
        .with_for_update()
    ).all()
    for variant in variants:
        if variant.stock < quantities[variant.id]:
            raise AppError(
                409,
                "OUT_OF_STOCK",
                f"Ya no hay suficientes unidades de {variant.product.name} "
                f"({variant.color} / {variant.size}). Revisa tu carrito.",
            )
        variant.stock -= quantities[variant.id]


def release_stock(db: Session, order: Order) -> None:
    for item in order.items:
        variant = db.get(ProductVariant, item.variant_id, with_for_update=True)
        if variant is not None:
            variant.stock += item.quantity


def start_payment(order: Order) -> Json:
    """Inicia el pago con Mercado Pago y devuelve a dónde redirigir al cliente.

    Sin MP_ACCESS_TOKEN se simula Checkout Pro: el pago se aprueba al instante y
    se vuelve directo a la confirmación, como lo haría Mercado Pago.
    """
    if not get_settings().mp_access_token:
        order.status = "PAID"
        return {"redirectUrl": f"/checkout/confirmacion/{order.id}?status=approved"}
    try:
        return {"redirectUrl": mercadopago.create_preference(order)}
    except mercadopago.PaymentGatewayError as exc:
        raise AppError(
            502,
            "PAYMENT_GATEWAY_ERROR",
            "No pudimos conectar con Mercado Pago. Tu pedido quedó guardado: "
            "intenta pagarlo de nuevo en unos minutos.",
        ) from exc
