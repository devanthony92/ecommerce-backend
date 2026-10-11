from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import Field
from sqlalchemy import select

from app.dependencies import DbSession, OptionalUser
from app.errors import AppError
from app.models import Product, ProductVariant
from app.schemas.base import CamelModel
from app.services.catalog import (
    DEFAULT_PAGE_SIZE,
    ProductFilters,
    list_categories,
    list_products,
    lookup_variants,
    product_detail,
)
from app.services.pricing import build_price_view

router = APIRouter(tags=["catalog"])

Json = dict[str, Any]


@router.get("/categories")
def get_categories(db: DbSession) -> list[Json]:
    return list_categories(db)


@router.get("/products")
def get_products(
    db: DbSession,
    user: OptionalUser,
    q: str = "",
    category: str | None = None,
    size: Annotated[list[str], Query()] = [],  # noqa: B006 (Query lo copia por solicitud)
    color: Annotated[list[str], Query()] = [],  # noqa: B006
    min_price: Annotated[int, Query(alias="minPrice", ge=0)] = 0,
    max_price: Annotated[int | None, Query(alias="maxPrice", ge=0)] = None,
    tag: str | None = None,
    on_sale: Annotated[bool, Query(alias="onSale")] = False,
    sort: str = "relevance",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1)] = DEFAULT_PAGE_SIZE,
) -> Json:
    filters = ProductFilters(
        q=q,
        category=category,
        sizes=size,
        colors=color,
        min_price=min_price,
        max_price=max_price,
        tag=tag,
        on_sale=on_sale,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return list_products(db, user, filters)


# Antes de /products/{slug}: si no, "lookup" se tomaría como un slug.
@router.get("/products/lookup")
def get_products_lookup(db: DbSession, user: OptionalUser, q: str = "") -> list[Json]:
    return lookup_variants(db, user, q)


@router.get("/products/{slug}")
def get_product(slug: str, db: DbSession, user: OptionalUser) -> Json:
    product = db.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        raise AppError(404, "PRODUCT_NOT_FOUND", "El producto no existe o ya no está disponible.")
    return product_detail(product, user)


class QuoteItem(CamelModel):
    variant_id: str
    quantity: int = Field(default=1)


class QuoteIn(CamelModel):
    items: list[QuoteItem] = Field(default_factory=list, max_length=100)


@router.post("/pricing/quote")
def quote(data: QuoteIn, db: DbSession, user: OptionalUser) -> Json:
    """Precio de cada variante a la cantidad pedida (con su escala)."""
    quoted = []
    for item in data.items:
        variant = db.get(ProductVariant, item.variant_id)
        if variant is None:
            raise AppError(
                404,
                "VARIANT_NOT_FOUND",
                "Una de las variantes no existe.",
                {"variantId": item.variant_id},
            )
        quantity = max(1, item.quantity)
        quoted.append(
            {
                "variantId": item.variant_id,
                "pricing": build_price_view(variant.product, user, quantity),
            }
        )
    return {"items": quoted}
