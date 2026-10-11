"""Catálogo: resúmenes, detalle, facetas y búsqueda (contrato §7 del frontend)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Product, ProductVariant, User
from app.services.pricing import build_price_view
from app.utils.text import normalize

Json = dict[str, Any]

DEFAULT_PAGE_SIZE = 12
MAX_PAGE_SIZE = 48
LOOKUP_LIMIT = 12


def variant_json(variant: ProductVariant) -> Json:
    return {
        "id": variant.id,
        "sku": variant.sku,
        "attributes": {"size": variant.size, "color": variant.color},
        "stock": variant.stock,
        "available": variant.available,
    }


def image_for_color(product: Product, color: str | None) -> Json:
    return next((image for image in product.images if image["color"] == color), product.images[0])


def product_summary(product: Product, user: User | None, color_filter: list[str] = ()) -> Json:
    # Con filtro de color, la imagen principal es la del primer color filtrado que tenga.
    image = next(
        (
            product.images[index]
            for index, color in enumerate(product.colors)
            if color["name"] in color_filter
        ),
        product.images[0],
    )
    category = product.category
    return {
        "id": product.id,
        "slug": product.slug,
        "name": product.name,
        "category": {"id": category.id, "slug": category.slug, "name": category.name},
        "image": image,
        "colors": product.colors,
        "tags": product.tags,
        "inStock": product.in_stock,
        "pricing": build_price_view(product, user, 1),
    }


def product_detail(product: Product, user: User | None) -> Json:
    return {
        **product_summary(product, user),
        "description": product.description,
        "images": product.images,
        "options": [
            {
                "name": "color",
                "label": "Color",
                "values": [color["name"] for color in product.colors],
            },
            {"name": "size", "label": "Talla", "values": product.sizes},
        ],
        "variants": [variant_json(variant) for variant in product.variants],
    }


def list_categories(db: Session) -> list[Json]:
    categories = db.scalars(select(Category).order_by(Category.position)).all()
    products = db.scalars(select(Product).order_by(Product.position)).all()
    result = []
    for category in categories:
        own = [product for product in products if product.category_id == category.id]
        result.append(
            {
                "id": category.id,
                "slug": category.slug,
                "name": category.name,
                "parentId": category.parent_id,
                "productCount": len(own),
                # Imagen representativa: la de su primer producto.
                "image": {"url": own[0].images[0]["url"], "alt": ""} if own else None,
            }
        )
    return result


@dataclass
class ProductFilters:
    q: str = ""
    category: str | None = None
    sizes: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    min_price: int = 0
    max_price: int | None = None
    tag: str | None = None
    on_sale: bool = False
    sort: str = "relevance"
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE


@dataclass
class _Row:
    product: Product
    summary: Json


SORTERS: dict[str, Callable[[_Row], Any]] = {
    # Destacados primero y luego los más vendidos (desempate por posición del catálogo).
    "relevance": lambda row: (
        "featured" not in row.product.tags,
        -row.product.sold,
        row.product.position,
    ),
    "price_asc": lambda row: (row.summary["pricing"]["unitPrice"], row.product.position),
    "price_desc": lambda row: (-row.summary["pricing"]["unitPrice"], row.product.position),
    "newest": lambda row: (-row.product.created_at.timestamp(), row.product.position),
    "bestsellers": lambda row: (-row.product.sold, row.product.position),
}


def _facets(rows: list[_Row]) -> Json:
    sizes: dict[str, int] = {}
    colors: dict[str, Json] = {}
    for row in rows:
        for size in row.product.sizes:
            sizes[size] = sizes.get(size, 0) + 1
        for color in row.product.colors:
            entry = colors.setdefault(
                color["name"], {"value": color["name"], "hex": color["hex"], "count": 0}
            )
            entry["count"] += 1
    prices = [row.summary["pricing"]["unitPrice"] for row in rows]
    return {
        "sizes": [{"value": value, "count": count} for value, count in sizes.items()],
        "colors": list(colors.values()),
        "priceRange": {"min": min(prices), "max": max(prices)} if prices else {"min": 0, "max": 0},
    }


def list_products(db: Session, user: User | None, filters: ProductFilters) -> Json:
    statement = select(Product).order_by(Product.position)
    category = db.scalar(select(Category).where(Category.slug == filters.category))
    if category is not None:
        statement = statement.where(Product.category_id == category.id)
    if filters.tag:
        statement = statement.where(Product.tags.any(filters.tag))
    if filters.on_sale:
        statement = statement.where(Product.promo_price.is_not(None))
    query = normalize(filters.q).strip()
    if query:
        statement = statement.where(Product.search_text.contains(query, autoescape=True))

    # Las facetas salen de esta base (búsqueda + categoría + tag) para que las
    # opciones no desaparezcan al elegir una.
    base = [
        _Row(product, product_summary(product, user, filters.colors))
        for product in db.scalars(statement).all()
    ]

    max_price = filters.max_price if filters.max_price is not None else float("inf")
    filtered = [
        row
        for row in base
        if (not filters.sizes or any(size in filters.sizes for size in row.product.sizes))
        and (
            not filters.colors
            or any(color["name"] in filters.colors for color in row.product.colors)
        )
        and filters.min_price <= row.summary["pricing"]["unitPrice"] <= max_price
    ]
    filtered.sort(key=SORTERS.get(filters.sort, SORTERS["relevance"]))

    page_size = min(MAX_PAGE_SIZE, max(1, filters.page_size))
    page = max(1, filters.page)
    total = len(filtered)
    start = (page - 1) * page_size
    return {
        "items": [row.summary for row in filtered[start : start + page_size]],
        "page": page,
        "pageSize": page_size,
        "total": total,
        "totalPages": max(1, -(-total // page_size)),
        "facets": _facets(base),
    }


def lookup_variants(db: Session, user: User | None, q: str) -> list[Json]:
    """Pedido rápido: variantes por nombre de producto o por SKU."""
    query = normalize(q).strip()
    if len(query) < 2:
        return []
    results: list[Json] = []
    for product in db.scalars(select(Product).order_by(Product.position)).all():
        name_matches = query in normalize(product.name)
        for variant in product.variants:
            if not name_matches and query not in normalize(variant.sku):
                continue
            image = image_for_color(product, variant.color)
            results.append(
                {
                    "variantId": variant.id,
                    "sku": variant.sku,
                    "productSlug": product.slug,
                    "productName": product.name,
                    "attributes": {"size": variant.size, "color": variant.color},
                    "available": variant.available,
                    "stock": variant.stock,
                    "image": {"url": image["url"], "alt": image["alt"]},
                    "pricing": build_price_view(product, user, 1),
                }
            )
            if len(results) >= LOOKUP_LIMIT:
                return results
    return results
