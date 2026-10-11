"""Reglas de negocio compartidas (las mismas que valida el frontend)."""

import re

# Celular colombiano: 10 dígitos que empiezan por 3.
PHONE_RE = re.compile(r"^3\d{9}$")

ROLES = ("BUYER", "WHOLESALE", "ADMIN")

# Departamentos de Colombia (más Bogotá D.C.).
DEPARTMENTS = (
    "Amazonas",
    "Antioquia",
    "Arauca",
    "Atlántico",
    "Bogotá D.C.",
    "Bolívar",
    "Boyacá",
    "Caldas",
    "Caquetá",
    "Casanare",
    "Cauca",
    "Cesar",
    "Chocó",
    "Córdoba",
    "Cundinamarca",
    "Guainía",
    "Guaviare",
    "Huila",
    "La Guajira",
    "Magdalena",
    "Meta",
    "Nariño",
    "Norte de Santander",
    "Putumayo",
    "Quindío",
    "Risaralda",
    "San Andrés y Providencia",
    "Santander",
    "Sucre",
    "Tolima",
    "Valle del Cauca",
    "Vaupés",
    "Vichada",
)

BASE_PERMISSIONS = (
    "cart.manage",
    "checkout.create",
    "orders.view",
    "favorites.manage",
    "lists.manage",
)

# Envío estándar: tarifa fija y gratis desde este valor en productos.
SHIPPING_COST = 10_000
FREE_SHIPPING_THRESHOLD = 120_000
EXPRESS_COST = 24_000
EXPRESS_CITIES = ("Medellín", "Bogotá", "Bogotá D.C.", "Cali", "Barranquilla")
PICKUP_ADDRESS = "Calle 30 # 65-12, Medellín"

# Programa mayorista: pedido mínimo en productos (sin envío).
WHOLESALE_MINIMUM_ORDER = 120_000
WHOLESALE_BENEFITS = (
    {"code": "TIER_PRICES", "label": "Precios por volumen desde media docena"},
    {"code": "QUICK_ORDER", "label": "Pedido rápido por referencia"},
    {"code": "LISTS", "label": "Listas de compra y recompra en un clic"},
    {"code": "PRIORITY_SUPPORT", "label": "Asesor comercial"},
)

ORDER_STATUS_GROUPS = {
    "active": ("PENDING_PAYMENT", "PAID", "PROCESSING", "SHIPPED"),
    "delivered": ("DELIVERED",),
    "cancelled": ("CANCELLED",),
}
CANCELLABLE_STATUSES = ("PENDING_PAYMENT", "PAID", "PROCESSING")
PAYMENT_METHODS = {
    "MERCADO_PAGO": {"label": "Mercado Pago", "status": "PENDING_PAYMENT"},
    "CASH_ON_DELIVERY": {"label": "Pago contra entrega", "status": "PROCESSING"},
}
