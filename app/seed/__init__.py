"""Datos semilla: catálogo de la tienda (mismos ids y SKUs que el frontend).

Idempotente: se puede ejecutar varias veces (actualiza en lugar de duplicar).
"""

import json
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Category, Product, ProductVariant
from app.utils.text import normalize

CATALOG_FILE = Path(__file__).with_name("catalog.json")


def load_catalog(db: Session) -> tuple[int, int, int]:
    data = json.loads(CATALOG_FILE.read_text("utf-8"))
    names = {category["id"]: category["name"] for category in data["categories"]}

    for category in data["categories"]:
        db.merge(
            Category(
                id=category["id"],
                slug=category["slug"],
                name=category["name"],
                parent_id=category["parentId"],
                position=category["position"],
            )
        )
    db.flush()

    variants = 0
    for item in data["products"]:
        db.merge(
            Product(
                id=item["id"],
                slug=item["slug"],
                name=item["name"],
                category_id=item["categoryId"],
                base_price=item["basePrice"],
                promo_price=item["promoPrice"],
                tier_defs=item["tierDefs"],
                tags=item["tags"],
                colors=item["colors"],
                sizes=item["sizes"],
                images=item["images"],
                description=item["description"],
                search_text=normalize(f"{item['name']} {names[item['categoryId']]}"),
                sold=item["sold"],
                position=item["position"],
                created_at=datetime.fromisoformat(item["createdAt"]),
            )
        )
        for position, variant in enumerate(item["variants"]):
            db.merge(
                ProductVariant(
                    id=variant["id"],
                    product_id=item["id"],
                    sku=variant["sku"],
                    size=variant["size"],
                    color=variant["color"],
                    stock=variant["stock"],
                    position=position,
                )
            )
            variants += 1
    db.commit()
    return len(data["categories"]), len(data["products"]), variants
