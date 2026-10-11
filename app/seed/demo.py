"""Cuentas de demostración para probar la tienda desplegada.

La contraseña es pública (está en el README): son cuentas de prueba sin datos reales.
Idempotente: si las cuentas ya existen, no hace nada.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import FREE_SHIPPING_THRESHOLD
from app.models import (
    Address,
    Favorite,
    Order,
    OrderItem,
    ProductVariant,
    ShoppingList,
    ShoppingListItem,
    User,
    WholesaleRequest,
)
from app.security import hash_password
from app.services.catalog import image_for_color
from app.services.pricing import build_price_view

DEMO_PASSWORD = "Trama1234"
BUYER_EMAIL = "comprador@demo.trama.co"
WHOLESALE_EMAIL = "mayorista@demo.trama.co"

STORE_ADDRESS = {
    "label": "Tienda",
    "recipient": "Carlos Pérez",
    "phone": "3004445566",
    "department": "Antioquia",
    "city": "Medellín",
    "line1": "Carrera 52 # 45-20, local 3",
    "line2": None,
    "notes": "Horario de recibo: 8 a.m. a 5 p.m.",
}

# Historial del mayorista: (fecha, estado, [(variante, cantidad)]).
ORDERS = (
    (
        "2026-08-20T15:30:00Z",
        "DELIVERED",
        [
            ("camiseta-basica-negro-m", 12),
            ("camiseta-basica-blanco-l", 12),
            ("gorra-beisbol-negro-única", 12),
        ],
    ),
    (
        "2026-09-12T18:10:00Z",
        "DELIVERED",
        [
            ("jean-slim-denim-32", 6),
            ("jean-slim-denim-30", 6),
            ("camiseta-oversize-negro-l", 6),
        ],
    ),
    (
        "2026-10-03T14:00:00Z",
        "SHIPPED",
        [("camiseta-basica-negro-m", 24), ("medias-pack-negro-única", 12)],
    ),
)


def _user(db: Session, email: str, name: str, role: str, phone: str | None = None) -> User:
    user = User(
        email=email,
        name=name,
        role=role,
        phone=phone,
        password_hash=hash_password(DEMO_PASSWORD),
        wholesale_status="APPROVED" if role == "WHOLESALE" else None,
    )
    db.add(user)
    db.flush()
    return user


def _order(db: Session, user: User, address: dict, created_at: str, status: str, lines) -> None:
    variants = {
        variant.id: variant
        for variant in db.scalars(
            select(ProductVariant).where(ProductVariant.id.in_([v for v, _ in lines]))
        ).all()
    }
    # La escala se calcula con las unidades del producto en el pedido.
    units: dict[str, int] = {}
    for variant_id, quantity in lines:
        product_id = variants[variant_id].product_id
        units[product_id] = units.get(product_id, 0) + quantity

    items = []
    for variant_id, quantity in lines:
        variant = variants[variant_id]
        view = build_price_view(variant.product, user, units[variant.product_id])
        image = image_for_color(variant.product, variant.color)
        items.append(
            OrderItem(
                product_id=variant.product_id,
                variant_id=variant.id,
                product_slug=variant.product.slug,
                name=variant.product.name,
                image={"url": image["url"], "alt": image["alt"]},
                attributes={"size": variant.size, "color": variant.color},
                quantity=quantity,
                unit_price=view["unitPrice"],
                line_total=view["unitPrice"] * quantity,
            )
        )
    total = sum(item.line_total for item in items)
    subtotal = sum(variants[i.variant_id].product.base_price * i.quantity for i in items)
    db.add(
        Order(
            user_id=user.id,
            status=status,
            items_count=sum(item.quantity for item in items),
            subtotal=subtotal,
            discount_total=subtotal - total,
            shipping_cost=0 if total >= FREE_SHIPPING_THRESHOLD else 10_000,
            total=total if total >= FREE_SHIPPING_THRESHOLD else total + 10_000,
            address=address,
            shipping={
                "id": "standard",
                "label": "Envío estándar",
                "estimatedDays": "3 a 5 días hábiles",
            },
            payment_method="MERCADO_PAGO",
            payment_reference="demo",
            created_at=datetime.fromisoformat(created_at),
            items=items,
        )
    )


def load_demo(db: Session) -> bool:
    if db.scalar(select(User.id).where(User.email == WHOLESALE_EMAIL)) is not None:
        return False

    _user(db, BUYER_EMAIL, "Laura Gómez", "BUYER")
    wholesale = _user(db, WHOLESALE_EMAIL, "Carlos Pérez", "WHOLESALE", phone="3004445566")

    address = Address(user_id=wholesale.id, is_default=True, **STORE_ADDRESS)
    db.add(address)
    db.flush()
    snapshot = {"id": address.id, **STORE_ADDRESS, "isDefault": True}

    db.add(
        WholesaleRequest(
            user_id=wholesale.id,
            status="APPROVED",
            submitted_at=datetime(2026, 3, 2, 14, tzinfo=UTC),
            reviewed_at=datetime(2026, 3, 4, 10, tzinfo=UTC),
            data={
                "tradeName": "Moda Carlos",
                "legalName": "Carlos Pérez",
                "nit": "900123456-7",
                "phone": "3004445566",
                "city": "Medellín",
                "address": "Carrera 52 # 45-20, local 3",
                "businessType": "PHYSICAL_STORE",
                "socialLinks": "@modacarlos",
                "estimatedMonthlyVolume": "1M_5M",
                "categoriesOfInterest": ["c-camisetas", "c-jeans"],
            },
        )
    )
    for created_at, status, lines in ORDERS:
        _order(db, wholesale, snapshot, created_at, status, lines)

    for product_id in ("p-camiseta-basica", "p-jean-slim", "p-gorra-beisbol"):
        db.add(Favorite(user_id=wholesale.id, product_id=product_id))

    db.add(
        ShoppingList(
            user_id=wholesale.id,
            name="Pedido mensual",
            updated_at=datetime(2026, 10, 1, 12, tzinfo=UTC),
            items=[
                ShoppingListItem(variant_id="camiseta-basica-negro-m", quantity=12),
                ShoppingListItem(variant_id="camiseta-basica-blanco-l", quantity=12),
                ShoppingListItem(variant_id="jean-slim-denim-30", quantity=6),
                ShoppingListItem(variant_id="gorra-beisbol-negro-única", quantity=12),
            ],
        )
    )
    db.commit()
    return True
