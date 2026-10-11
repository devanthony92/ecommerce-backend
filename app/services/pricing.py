"""Motor de precios. El frontend nunca calcula precios: solo muestra este PriceView.

Cadena: precio base → promoción → escala por cantidad (solo mayoristas).
"""

import math
from typing import Any

from app.models import Product, User

Json = dict[str, Any]


def round_cop(amount: float) -> int:
    """Redondea a la centena más cercana (las mitades hacia arriba, como en el frontend)."""
    return math.floor(amount / 100 + 0.5) * 100


def round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def audience_for(user: User | None) -> str:
    if user is None:
        return "PUBLIC"
    return "WHOLESALE" if user.role == "WHOLESALE" else "BUYER"


def build_price_view(product: Product, user: User | None, quantity: int = 1) -> Json:
    audience = audience_for(user)
    list_price = product.base_price
    base_unit = product.promo_price if product.promo_price is not None else list_price

    def price_for(definition: Json) -> int:
        return round_cop(base_unit * (1 - definition["discountPercent"] / 100))

    # Las escalas por cantidad son exclusivas de las cuentas mayoristas.
    definitions = product.tier_defs if audience == "WHOLESALE" else product.tier_defs[:1]
    current = next(
        (d for d in reversed(definitions) if d["minQty"] <= quantity),
        definitions[0],
    )
    upcoming = next((d for d in definitions if d["minQty"] > quantity), None)
    unit_price = price_for(current)

    tiers: list[Json] = []
    if len(definitions) > 1:
        for index, definition in enumerate(definitions):
            tier_price = price_for(definition)
            tiers.append(
                {
                    "minQty": definition["minQty"],
                    "label": definition["label"],
                    "unitPrice": tier_price,
                    "savingsPercent": round_half_up((1 - tier_price / list_price) * 100),
                    "isCurrent": definition is current,
                    "isBest": index == len(definitions) - 1,
                }
            )

    applied_rules: list[Json] = []
    if product.promo_price is not None:
        applied_rules.append({"type": "PROMOTION", "label": "Precio de temporada"})
    if current["minQty"] > 1:
        applied_rules.append(
            {"type": "QUANTITY_TIER", "label": current["label"], "minQty": current["minQty"]}
        )

    unit_savings = list_price - unit_price

    return {
        "currency": "COP",
        "audience": audience,
        "quantity": quantity,
        "listPrice": list_price,
        "unitPrice": unit_price,
        "compareAtPrice": list_price if product.promo_price is not None else None,
        "lineTotal": unit_price * quantity,
        "savings": {
            "unit": unit_savings,
            "total": unit_savings * quantity,
            "percent": round_half_up(unit_savings / list_price * 100),
        },
        "appliedRules": applied_rules,
        "tiers": tiers,
        "nextTier": upcoming
        and {
            "minQty": upcoming["minQty"],
            "label": upcoming["label"],
            "unitPrice": price_for(upcoming),
            "unitsToReach": upcoming["minQty"] - quantity,
        },
    }
