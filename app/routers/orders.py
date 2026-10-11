from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, status
from pydantic import Field, StringConstraints
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.constants import CANCELLABLE_STATUSES, ORDER_STATUS_GROUPS, PAYMENT_METHODS
from app.dependencies import CurrentUser, DbSession
from app.errors import AppError, not_found
from app.models import Address, CartItem, Order, OrderItem, ProductVariant, User
from app.routers.addresses import address_json
from app.schemas.base import CamelModel
from app.services.cart import user_cart, user_lines
from app.services.orders import (
    order_json,
    release_stock,
    reserve_stock,
    shipping_options,
    start_payment,
)
from app.utils.money import format_cop

router = APIRouter(tags=["orders"])

Json = dict[str, Any]


class OrderIn(CamelModel):
    address_id: int
    shipping_option_id: str = Field(max_length=20)
    payment_method: str = Field(max_length=30)
    notes: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class CancelIn(CamelModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


def _own_address(db: Session, user: User, address_id: int | None) -> Address | None:
    address = db.get(Address, address_id) if address_id is not None else None
    return address if address is not None and address.user_id == user.id else None


def _own_order(db: Session, user: User, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if order is None or order.user_id != user.id:
        raise not_found("El pedido no existe.")
    return order


@router.get("/checkout/shipping-options")
def get_shipping_options(
    user: CurrentUser, db: DbSession, address_id: Annotated[int, Query(alias="addressId")]
) -> list[Json]:
    address = _own_address(db, user, address_id)
    if address is None:
        raise AppError(404, "ADDRESS_NOT_FOUND", "Elige una dirección válida.")
    return shipping_options(user_cart(db, user), address)


@router.post("/orders", status_code=status.HTTP_201_CREATED)
def create_order(data: OrderIn, user: CurrentUser, db: DbSession) -> Json:
    cart = user_cart(db, user)
    items = [item for item in cart["items"] if item["available"]]
    if not items:
        raise AppError(422, "CART_EMPTY", "Tu carrito no tiene productos disponibles.")
    minimum = cart["minimumOrder"]
    if minimum and not minimum["met"]:
        raise AppError(
            422,
            "MINIMUM_ORDER_NOT_MET",
            f"El pedido mínimo mayorista es de {format_cop(minimum['amount'])} en productos.",
        )
    address = _own_address(db, user, data.address_id)
    if address is None:
        raise AppError(422, "ADDRESS_REQUIRED", "Elige una dirección de entrega.")
    option = next(
        (o for o in shipping_options(cart, address) if o["id"] == data.shipping_option_id), None
    )
    if option is None:
        raise AppError(422, "SHIPPING_REQUIRED", "Elige una opción de envío.")
    payment = PAYMENT_METHODS.get(data.payment_method)
    if payment is None:
        raise AppError(422, "PAYMENT_REQUIRED", "Elige un medio de pago.")

    reserve_stock(db, {item["variant"]["id"]: item["quantity"] for item in items})

    order = Order(
        user_id=user.id,
        status=payment["status"],
        items_count=cart["summary"]["itemsCount"],
        subtotal=cart["summary"]["subtotal"],
        discount_total=cart["summary"]["discountTotal"],
        shipping_cost=option["price"],
        total=option["total"],
        address=address_json(address),
        shipping={
            "id": option["id"],
            "label": option["label"],
            "estimatedDays": option["estimatedDays"],
        },
        payment_method=data.payment_method,
        notes=data.notes or None,
        items=[
            OrderItem(
                product_id=item["productId"],
                variant_id=item["variant"]["id"],
                product_slug=item["productSlug"],
                name=item["name"],
                image=item["image"],
                attributes=item["variant"]["attributes"],
                quantity=item["quantity"],
                unit_price=item["pricing"]["unitPrice"],
                line_total=item["pricing"]["lineTotal"],
            )
            for item in items
        ],
    )
    db.add(order)
    # El pedido se lleva lo disponible; lo agotado se queda en el carrito.
    db.execute(
        delete(CartItem).where(
            CartItem.user_id == user.id,
            CartItem.variant_id.in_([item["variant"]["id"] for item in items]),
        )
    )
    db.flush()

    checkout = {"redirectUrl": None}
    if data.payment_method == "MERCADO_PAGO":
        # El pedido y el stock se guardan antes de hablar con Mercado Pago: si la
        # pasarela falla, el cliente puede reintentar el pago desde la confirmación.
        db.commit()
        checkout = start_payment(order)
    db.commit()
    return {"order": order_json(order), "payment": checkout}


@router.post("/orders/{order_id}/payment")
def retry_payment(order_id: int, user: CurrentUser, db: DbSession) -> Json:
    """Nuevo intento de pago de un pedido pendiente (p. ej. si el pago fue rechazado)."""
    order = _own_order(db, user, order_id)
    if order.status != "PENDING_PAYMENT" or order.payment_method != "MERCADO_PAGO":
        raise AppError(422, "ORDER_NOT_PAYABLE", "Este pedido no tiene pagos pendientes.")
    checkout = start_payment(order)
    db.commit()
    return checkout


@router.get("/orders")
def list_orders(
    user: CurrentUser,
    db: DbSession,
    group: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1)] = 10,
) -> Json:
    page_size = min(20, page_size)
    statement = select(Order).where(Order.user_id == user.id)
    statuses = ORDER_STATUS_GROUPS.get(group or "")
    if statuses:
        statement = statement.where(Order.status.in_(statuses))
    total = db.scalar(select(func.count()).select_from(statement.subquery()))
    orders = db.scalars(
        statement.order_by(Order.created_at.desc(), Order.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [order_json(order) for order in orders],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": max(1, -(-total // page_size)),
    }


@router.get("/orders/{order_id}")
def get_order(order_id: int, user: CurrentUser, db: DbSession) -> Json:
    return order_json(_own_order(db, user, order_id))


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int, data: CancelIn, user: CurrentUser, db: DbSession) -> Json:
    order = _own_order(db, user, order_id)
    if order.status not in CANCELLABLE_STATUSES:
        raise AppError(
            422,
            "ORDER_NOT_CANCELLABLE",
            "Este pedido ya salió de bodega y no se puede cancelar.",
        )
    order.status = "CANCELLED"
    order.cancelled_at = datetime.now(UTC)
    order.cancel_reason = data.reason or None
    # Las unidades vuelven al inventario.
    release_stock(db, order)
    db.commit()
    return order_json(order)


@router.post("/orders/{order_id}/reorder")
def reorder(order_id: int, user: CurrentUser, db: DbSession) -> Json:
    """Agrega al carrito lo del pedido que siga disponible."""
    order = _own_order(db, user, order_id)
    lines = {line.variant_id: line for line in user_lines(db, user)}
    skipped = []
    for item in order.items:
        variant = db.get(ProductVariant, item.variant_id)
        if variant is None or not variant.available:
            skipped.append(item)
            continue
        if item.variant_id in lines:
            lines[item.variant_id].quantity += item.quantity
        else:
            line = CartItem(user_id=user.id, variant_id=item.variant_id, quantity=item.quantity)
            db.add(line)
            lines[item.variant_id] = line
    db.flush()

    cart = user_cart(db, user)
    for item in skipped:
        cart["warnings"].append(
            {
                "code": "REORDER_UNAVAILABLE",
                "cartItemId": item.variant_id,
                "message": f"{item.name} ({item.attributes['color']} / "
                f"{item.attributes['size']}) ya no está disponible.",
            }
        )
    return cart
