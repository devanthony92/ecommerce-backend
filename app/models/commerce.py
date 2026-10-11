from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CartItem(Base):
    """Línea del carrito de un usuario con sesión (el de invitado vive en el navegador)."""

    __tablename__ = "cart_items"
    __table_args__ = (UniqueConstraint("user_id", "variant_id", name="uq_cart_items_user_variant"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("product_variants.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # PENDING_PAYMENT | PAID | PROCESSING | SHIPPED | DELIVERED | CANCELLED
    status: Mapped[str] = mapped_column(String(20), index=True)
    items_count: Mapped[int] = mapped_column(Integer)
    # Totales en COP: subtotal a precio público, descuento y total con envío.
    subtotal: Mapped[int] = mapped_column(Integer)
    discount_total: Mapped[int] = mapped_column(Integer)
    shipping_cost: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    # Copias al momento de comprar: si luego cambian, el pedido no cambia.
    address: Mapped[dict] = mapped_column(JSONB)
    shipping: Mapped[dict] = mapped_column(JSONB)
    payment_method: Mapped[str] = mapped_column(String(30))
    # Id del pago en Mercado Pago (cuando se confirma por webhook).
    payment_reference: Mapped[str | None] = mapped_column(String(64), default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    cancel_reason: Mapped[str | None] = mapped_column(Text, default=None)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderItem.id",
        lazy="selectin",
    )

    @property
    def number(self) -> str:
        return f"PED-{self.id:06d}"


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    variant_id: Mapped[str] = mapped_column(ForeignKey("product_variants.id"), index=True)
    product_slug: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(120))
    # {url, alt} y {size, color} al momento de comprar.
    image: Mapped[dict] = mapped_column(JSONB)
    attributes: Mapped[dict] = mapped_column(JSONB)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[int] = mapped_column(Integer)
    line_total: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")
