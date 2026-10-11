"""Carrito (contrato §7): precios, avisos de stock, incentivos y pedido mínimo.

Regla comercial: la escala por cantidad usa el total de unidades del mismo
producto en el carrito, sumando tallas y colores.
"""

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import FREE_SHIPPING_THRESHOLD, SHIPPING_COST, WHOLESALE_MINIMUM_ORDER
from app.models import CartItem, ProductVariant, User
from app.services.catalog import image_for_color
from app.services.pricing import build_price_view, round_half_up

Json = dict[str, Any]


class Line(Protocol):
    id: Any
    variant_id: str
    quantity: int


@dataclass
class GuestLine:
    """Línea de invitado: el carrito no se guarda y su id es el de la variante."""

    id: str
    variant_id: str
    quantity: int


def _label(variant: ProductVariant) -> str:
    return f"{variant.color} / {variant.size}"


def load_variants(db: Session, variant_ids: list[str]) -> dict[str, ProductVariant]:
    if not variant_ids:
        return {}
    variants = db.scalars(select(ProductVariant).where(ProductVariant.id.in_(variant_ids))).all()
    return {variant.id: variant for variant in variants}


def user_lines(db: Session, user: User) -> list[CartItem]:
    return list(
        db.scalars(select(CartItem).where(CartItem.user_id == user.id).order_by(CartItem.id)).all()
    )


def build_cart(db: Session, lines: list[Line], user: User | None, cart_id: str = "guest") -> Json:
    """Arma el Cart. Ajusta al stock las cantidades que lo superan (modifica las
    líneas, para que el carrito guardado quede corregido) y avisa en `warnings`."""
    variants = load_variants(db, [line.variant_id for line in lines])
    resolved = [(line, variants[line.variant_id]) for line in lines if line.variant_id in variants]
    warnings: list[Json] = []

    for line, variant in resolved:
        product = variant.product
        if variant.available and line.quantity > variant.stock:
            line.quantity = variant.stock
            warnings.append(
                {
                    "code": "STOCK_REDUCED",
                    "cartItemId": line.id,
                    "message": f"Solo hay {variant.stock} unidades de {product.name} "
                    f"({_label(variant)}). Ajustamos la cantidad.",
                }
            )
        if not variant.available:
            warnings.append(
                {
                    "code": "OUT_OF_STOCK",
                    "cartItemId": line.id,
                    "message": f"{product.name} ({_label(variant)}) se agotó. "
                    "No se incluye en el total.",
                }
            )

    units_by_product: dict[str, int] = {}
    for line, variant in resolved:
        if variant.available:
            units_by_product[variant.product_id] = (
                units_by_product.get(variant.product_id, 0) + line.quantity
            )

    items: list[Json] = []
    for line, variant in resolved:
        product = variant.product
        product_units = units_by_product.get(product.id, line.quantity)
        view = build_price_view(product, user, product_units)
        unit_savings = view["listPrice"] - view["unitPrice"]
        image = image_for_color(product, variant.color)
        items.append(
            {
                "id": line.id,
                "productId": product.id,
                "productSlug": product.slug,
                "name": product.name,
                "image": {"url": image["url"], "alt": image["alt"]},
                "variant": {
                    "id": variant.id,
                    "sku": variant.sku,
                    "attributes": {"size": variant.size, "color": variant.color},
                    "stock": variant.stock,
                },
                "available": variant.available,
                "quantity": line.quantity,
                # Unidades del producto que definen la escala (todas sus variantes).
                "productQuantity": product_units,
                "pricing": {
                    **view,
                    "quantity": line.quantity,
                    "lineTotal": view["unitPrice"] * line.quantity,
                    "savings": {
                        "unit": unit_savings,
                        "total": unit_savings * line.quantity,
                        "percent": view["savings"]["percent"],
                    },
                },
                # Para cambiar talla o color desde el carrito.
                "variantOptions": [
                    {
                        "id": option.id,
                        "attributes": {"size": option.size, "color": option.color},
                        "available": option.available,
                    }
                    for option in product.variants
                ],
            }
        )

    billable = [item for item in items if item["available"]]
    items_total = sum(item["pricing"]["lineTotal"] for item in billable)
    subtotal = sum(item["pricing"]["listPrice"] * item["quantity"] for item in billable)
    discount_total = subtotal - items_total
    free_shipping = items_total >= FREE_SHIPPING_THRESHOLD
    shipping = 0 if not billable or free_shipping else SHIPPING_COST

    incentives: list[Json] = []
    for product_id, units in units_by_product.items():
        product = next(v.product for v in variants.values() if v.product_id == product_id)
        upcoming = build_price_view(product, user, units)["nextTier"]
        if not upcoming:
            continue
        incentives.append(
            {
                "type": "QUANTITY_TIER",
                "productId": product_id,
                "productName": product.name,
                "current": units,
                "target": upcoming["minQty"],
                "remaining": upcoming["unitsToReach"],
                "targetLabel": upcoming["label"],
                "targetUnitPrice": upcoming["unitPrice"],
                "progressPercent": round_half_up(units / upcoming["minQty"] * 100),
            }
        )
    if billable:
        incentives.append(
            {
                "type": "FREE_SHIPPING",
                "achieved": free_shipping,
                "current": items_total,
                "target": FREE_SHIPPING_THRESHOLD,
                "remaining": max(0, FREE_SHIPPING_THRESHOLD - items_total),
                "progressPercent": min(
                    100, round_half_up(items_total / FREE_SHIPPING_THRESHOLD * 100)
                ),
            }
        )

    # Pedido mínimo: solo mayoristas, medido con el valor de los productos.
    minimum_order = None
    if user is not None and user.role == "WHOLESALE":
        minimum_order = {
            "amount": WHOLESALE_MINIMUM_ORDER,
            "remaining": max(0, WHOLESALE_MINIMUM_ORDER - items_total),
            "met": items_total >= WHOLESALE_MINIMUM_ORDER,
        }

    return {
        "id": cart_id,
        "items": items,
        "summary": {
            "itemsCount": sum(item["quantity"] for item in billable),
            "subtotal": subtotal,
            "discountTotal": discount_total,
            "shipping": shipping,
            "total": items_total + shipping,
            "savingsTotal": discount_total,
        },
        "incentives": incentives,
        "warnings": warnings,
        "minimumOrder": minimum_order,
    }


def user_cart(db: Session, user: User) -> Json:
    """Carrito guardado del usuario. Persiste los ajustes de stock que haga build_cart."""
    lines = user_lines(db, user)
    cart = build_cart(db, lines, user, f"cart-{user.id}")
    db.commit()
    return cart
