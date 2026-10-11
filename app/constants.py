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
