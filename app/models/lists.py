from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Favorite(Base):
    __tablename__ = "favorites"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ShoppingList(Base):
    """Lista de compra recurrente ("Pedido mensual"): variantes con su cantidad habitual."""

    __tablename__ = "shopping_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["ShoppingListItem"]] = relationship(
        back_populates="shopping_list",
        cascade="all, delete-orphan",
        order_by="ShoppingListItem.id",
        lazy="selectin",
    )


class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"
    __table_args__ = (UniqueConstraint("list_id", "variant_id", name="uq_list_items_variant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(
        ForeignKey("shopping_lists.id", ondelete="CASCADE"), index=True
    )
    variant_id: Mapped[str] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer)

    shopping_list: Mapped[ShoppingList] = relationship(back_populates="items")
