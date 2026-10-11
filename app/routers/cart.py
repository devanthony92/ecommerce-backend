from typing import Any

from fastapi import APIRouter
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dependencies import CurrentUser, DbSession, OptionalUser
from app.errors import AppError
from app.models import CartItem, ProductVariant, User
from app.schemas.base import CamelModel
from app.services.cart import GuestLine, build_cart, user_cart

router = APIRouter(prefix="/cart", tags=["cart"])

Json = dict[str, Any]


class ItemIn(CamelModel):
    variant_id: str = Field(min_length=1, max_length=120)
    quantity: int


class ItemsIn(CamelModel):
    items: list[ItemIn] = Field(default_factory=list, max_length=200)


class ItemUpdateIn(CamelModel):
    variant_id: str | None = None
    quantity: int | None = None


def _out_of_stock(message: str) -> AppError:
    return AppError(409, "OUT_OF_STOCK", message)


def _check_addable(db: Session, item: ItemIn) -> ProductVariant:
    variant = db.get(ProductVariant, item.variant_id)
    if variant is None:
        raise AppError(404, "VARIANT_NOT_FOUND", "El producto no existe.")
    if not variant.available:
        raise _out_of_stock(f"{variant.product.name} está agotado en esa talla y color.")
    if item.quantity <= 0:
        raise AppError(400, "VALIDATION_ERROR", "La cantidad debe ser mayor a cero.")
    return variant


def _add(db: Session, user: User, variant_id: str, quantity: int) -> None:
    """Suma unidades a la línea de la variante o crea una nueva."""
    line = db.scalar(
        select(CartItem).where(CartItem.user_id == user.id, CartItem.variant_id == variant_id)
    )
    if line is None:
        db.add(CartItem(user_id=user.id, variant_id=variant_id, quantity=quantity))
    else:
        line.quantity += quantity
    db.flush()


@router.get("")
def get_cart(user: CurrentUser, db: DbSession) -> Json:
    return user_cart(db, user)


@router.post("/items")
def add_item(data: ItemIn, user: CurrentUser, db: DbSession) -> Json:
    _check_addable(db, data)
    _add(db, user, data.variant_id, data.quantity)
    return user_cart(db, user)


@router.post("/items/bulk")
def add_items(data: ItemsIn, user: CurrentUser, db: DbSession) -> Json:
    # Los ítems inexistentes o sin stock se omiten; el resto se agrega.
    for item in data.items:
        try:
            _check_addable(db, item)
        except AppError:
            continue
        _add(db, user, item.variant_id, item.quantity)
    return user_cart(db, user)


@router.patch("/items/{item_id}")
def update_item(item_id: int, data: ItemUpdateIn, user: CurrentUser, db: DbSession) -> Json:
    line = db.get(CartItem, item_id)
    if line is None or line.user_id != user.id:
        raise AppError(404, "CART_ITEM_NOT_FOUND", "El producto ya no está en tu carrito.")

    if data.variant_id and data.variant_id != line.variant_id:
        variant = db.get(ProductVariant, data.variant_id)
        if variant is None or not variant.available:
            raise _out_of_stock("Esa combinación no tiene stock.")
        # Si la nueva variante ya está en el carrito, se unen las líneas.
        target = db.scalar(
            select(CartItem).where(
                CartItem.user_id == user.id, CartItem.variant_id == data.variant_id
            )
        )
        if target is not None:
            target.quantity += line.quantity
            db.delete(line)
            line = target
        else:
            line.variant_id = data.variant_id

    if data.quantity is not None:
        if data.quantity <= 0:
            db.delete(line)
        else:
            line.quantity = data.quantity
    db.flush()
    return user_cart(db, user)


@router.delete("/items/{item_id}")
def remove_item(item_id: int, user: CurrentUser, db: DbSession) -> Json:
    line = db.get(CartItem, item_id)
    if line is not None and line.user_id == user.id:
        db.delete(line)
        db.flush()
    return user_cart(db, user)


@router.post("/merge")
def merge(data: ItemsIn, user: CurrentUser, db: DbSession) -> Json:
    """Al iniciar sesión, el carrito de invitado se suma al del usuario."""
    for item in data.items:
        if item.quantity > 0 and db.get(ProductVariant, item.variant_id) is not None:
            _add(db, user, item.variant_id, item.quantity)
    return user_cart(db, user)


@router.post("/quote")
def quote(data: ItemsIn, db: DbSession, user: OptionalUser) -> Json:
    """Invitado: calcula el carrito sin guardarlo."""
    lines = [
        GuestLine(id=item.variant_id, variant_id=item.variant_id, quantity=item.quantity)
        for item in data.items
        if item.quantity > 0
    ]
    return build_cart(db, lines, user)
