from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Response, status
from pydantic import Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencies import CurrentUser, DbSession
from app.errors import AppError
from app.models import (
    CartItem,
    Favorite,
    Product,
    ProductVariant,
    ShoppingList,
    ShoppingListItem,
    User,
)
from app.schemas.base import CamelModel
from app.services.cart import load_variants, user_cart, user_lines
from app.services.catalog import image_for_color, product_summary
from app.services.pricing import build_price_view

router = APIRouter(tags=["lists"])

Json = dict[str, Any]
NO_CONTENT = status.HTTP_204_NO_CONTENT


def _no_content() -> Response:
    return Response(status_code=NO_CONTENT)


# --- Favoritos -------------------------------------------------------------------


@router.get("/favorites")
def list_favorites(user: CurrentUser, db: DbSession) -> list[Json]:
    products = db.scalars(
        select(Product)
        .join(Favorite, Favorite.product_id == Product.id)
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc(), Product.position)
    ).all()
    return [product_summary(product, user) for product in products]


@router.put("/favorites/{product_id}", status_code=NO_CONTENT)
def add_favorite(product_id: str, user: CurrentUser, db: DbSession) -> Response:
    if db.get(Product, product_id) is None:
        raise AppError(404, "PRODUCT_NOT_FOUND", "El producto no existe.")
    if db.get(Favorite, (user.id, product_id)) is None:
        db.add(Favorite(user_id=user.id, product_id=product_id))
        db.commit()
    return _no_content()


@router.delete("/favorites/{product_id}", status_code=NO_CONTENT)
def remove_favorite(product_id: str, user: CurrentUser, db: DbSession) -> Response:
    favorite = db.get(Favorite, (user.id, product_id))
    if favorite is not None:
        db.delete(favorite)
        db.commit()
    return _no_content()


# --- Listas ----------------------------------------------------------------------

ListName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]


class ListIn(CamelModel):
    name: ListName


class ListItemIn(CamelModel):
    variant_id: str = Field(min_length=1, max_length=120)
    quantity: int


class ListItemUpdateIn(CamelModel):
    quantity: int


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _touch(shopping_list: ShoppingList) -> None:
    shopping_list.updated_at = datetime.now(UTC)


def _list_summary(db: Session, shopping_list: ShoppingList) -> Json:
    variants = load_variants(db, [item.variant_id for item in shopping_list.items])
    previews = []
    for item in shopping_list.items[:3]:
        variant = variants.get(item.variant_id)
        if variant is not None:
            previews.append(
                {"url": image_for_color(variant.product, variant.color)["url"], "alt": ""}
            )
    return {
        "id": shopping_list.id,
        "name": shopping_list.name,
        "updatedAt": _iso(shopping_list.updated_at),
        "itemsCount": len(shopping_list.items),
        "unitsCount": sum(item.quantity for item in shopping_list.items),
        "previews": previews,
    }


def _list_item(item: ShoppingListItem, variant: ProductVariant, user: User) -> Json:
    product = variant.product
    image = image_for_color(product, variant.color)
    return {
        "id": item.id,
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
        "quantity": item.quantity,
        "pricing": build_price_view(product, user, item.quantity),
    }


def _own_list(db: Session, user: User, list_id: int) -> ShoppingList:
    shopping_list = db.get(ShoppingList, list_id)
    if shopping_list is None or shopping_list.user_id != user.id:
        raise AppError(404, "LIST_NOT_FOUND", "La lista no existe.")
    return shopping_list


def _check_name(db: Session, user: User, name: str, except_id: int | None = None) -> None:
    """El nombre es único por usuario, sin importar mayúsculas."""
    statement = select(ShoppingList.id).where(
        ShoppingList.user_id == user.id, func.lower(ShoppingList.name) == name.lower()
    )
    if except_id is not None:
        statement = statement.where(ShoppingList.id != except_id)
    if db.scalar(statement) is not None:
        message = "Ya tienes una lista con ese nombre."
        raise AppError(400, "VALIDATION_ERROR", message, {"name": message})


def _positive(quantity: int) -> None:
    if quantity <= 0:
        raise AppError(400, "VALIDATION_ERROR", "La cantidad debe ser mayor a cero.")


@router.get("/lists")
def list_lists(user: CurrentUser, db: DbSession) -> list[Json]:
    lists = db.scalars(
        select(ShoppingList)
        .where(ShoppingList.user_id == user.id)
        .order_by(ShoppingList.updated_at.desc(), ShoppingList.id.desc())
    ).all()
    return [_list_summary(db, shopping_list) for shopping_list in lists]


@router.post("/lists", status_code=status.HTTP_201_CREATED)
def create_list(data: ListIn, user: CurrentUser, db: DbSession) -> Json:
    _check_name(db, user, data.name)
    shopping_list = ShoppingList(user_id=user.id, name=data.name, updated_at=datetime.now(UTC))
    db.add(shopping_list)
    db.commit()
    return _list_summary(db, shopping_list)


@router.get("/lists/{list_id}")
def get_list(list_id: int, user: CurrentUser, db: DbSession) -> Json:
    shopping_list = _own_list(db, user, list_id)
    variants = load_variants(db, [item.variant_id for item in shopping_list.items])
    return {
        **_list_summary(db, shopping_list),
        "items": [
            _list_item(item, variants[item.variant_id], user)
            for item in shopping_list.items
            if item.variant_id in variants
        ],
    }


@router.patch("/lists/{list_id}")
def rename_list(list_id: int, data: ListIn, user: CurrentUser, db: DbSession) -> Json:
    shopping_list = _own_list(db, user, list_id)
    _check_name(db, user, data.name, except_id=shopping_list.id)
    shopping_list.name = data.name
    _touch(shopping_list)
    db.commit()
    return _list_summary(db, shopping_list)


@router.delete("/lists/{list_id}", status_code=NO_CONTENT)
def delete_list(list_id: int, user: CurrentUser, db: DbSession) -> Response:
    shopping_list = db.get(ShoppingList, list_id)
    if shopping_list is not None and shopping_list.user_id == user.id:
        db.delete(shopping_list)
        db.commit()
    return _no_content()


@router.post("/lists/{list_id}/items")
def add_list_item(list_id: int, data: ListItemIn, user: CurrentUser, db: DbSession) -> Json:
    """Si la variante ya está en la lista, se suma la cantidad."""
    shopping_list = _own_list(db, user, list_id)
    if db.get(ProductVariant, data.variant_id) is None:
        raise AppError(404, "VARIANT_NOT_FOUND", "El producto no existe.")
    _positive(data.quantity)
    existing = next(
        (item for item in shopping_list.items if item.variant_id == data.variant_id), None
    )
    if existing is not None:
        existing.quantity += data.quantity
    else:
        shopping_list.items.append(
            ShoppingListItem(variant_id=data.variant_id, quantity=data.quantity)
        )
    _touch(shopping_list)
    db.commit()
    return _list_summary(db, shopping_list)


def _own_item(db: Session, user: User, list_id: int, item_id: int) -> ShoppingListItem:
    item = db.get(ShoppingListItem, item_id)
    if item is None or item.list_id != list_id or item.shopping_list.user_id != user.id:
        raise AppError(404, "LIST_ITEM_NOT_FOUND", "El producto ya no está en la lista.")
    return item


@router.patch("/lists/{list_id}/items/{item_id}")
def update_list_item(
    list_id: int, item_id: int, data: ListItemUpdateIn, user: CurrentUser, db: DbSession
) -> Json:
    item = _own_item(db, user, list_id, item_id)
    _positive(data.quantity)
    item.quantity = data.quantity
    _touch(item.shopping_list)
    db.commit()
    return _list_item(item, db.get(ProductVariant, item.variant_id), user)


@router.delete("/lists/{list_id}/items/{item_id}", status_code=NO_CONTENT)
def remove_list_item(list_id: int, item_id: int, user: CurrentUser, db: DbSession) -> Response:
    shopping_list = _own_list(db, user, list_id)
    item = next((entry for entry in shopping_list.items if entry.id == item_id), None)
    if item is not None:
        shopping_list.items.remove(item)
    _touch(shopping_list)
    db.commit()
    return _no_content()


@router.post("/lists/{list_id}/add-to-cart")
def add_list_to_cart(list_id: int, user: CurrentUser, db: DbSession) -> Json:
    """Agrega al carrito lo disponible; lo agotado viene en `warnings`."""
    shopping_list = _own_list(db, user, list_id)
    variants = load_variants(db, [item.variant_id for item in shopping_list.items])
    lines = {line.variant_id: line for line in user_lines(db, user)}
    skipped: list[ProductVariant] = []
    for item in shopping_list.items:
        variant = variants.get(item.variant_id)
        if variant is None:
            continue
        if not variant.available:
            skipped.append(variant)
            continue
        if item.variant_id in lines:
            lines[item.variant_id].quantity += item.quantity
        else:
            line = CartItem(user_id=user.id, variant_id=item.variant_id, quantity=item.quantity)
            db.add(line)
            lines[item.variant_id] = line
    db.flush()

    cart = user_cart(db, user)
    for variant in skipped:
        cart["warnings"].append(
            {
                "code": "LIST_ITEM_UNAVAILABLE",
                "cartItemId": variant.id,
                "message": f"{variant.product.name} ({variant.color} / {variant.size}) "
                "está agotado.",
            }
        )
    return cart
