from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Category(Base):
    __tablename__ = "categories"

    # Ids legibles (`c-camisetas`): los mismos que usa el frontend.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("categories.id"), default=None)
    position: Mapped[int] = mapped_column(Integer, default=0)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"), index=True)
    # Dinero en enteros COP, IVA incluido.
    base_price: Mapped[int] = mapped_column(Integer)
    promo_price: Mapped[int | None] = mapped_column(Integer, default=None)
    # Escalas por cantidad: [{minQty, label, discountPercent}] (solo mayoristas).
    tier_defs: Mapped[list[dict]] = mapped_column(JSONB)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), default=list)
    # [{name, hex}]
    colors: Mapped[list[dict]] = mapped_column(JSONB)
    sizes: Mapped[list[str]] = mapped_column(JSONB)
    # [{url, alt, color, width, height}], una por color.
    images: Mapped[list[dict]] = mapped_column(JSONB)
    description: Mapped[str] = mapped_column(Text)
    # Nombre + categoría en minúsculas y sin tildes, para la búsqueda.
    search_text: Mapped[str] = mapped_column(String(300))
    sold: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    category: Mapped[Category] = relationship(back_populates="products", lazy="joined")
    variants: Mapped[list["ProductVariant"]] = relationship(
        back_populates="product", order_by="ProductVariant.position", lazy="selectin"
    )

    @property
    def in_stock(self) -> bool:
        return any(variant.available for variant in self.variants)


class ProductVariant(Base):
    __tablename__ = "product_variants"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), index=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    size: Mapped[str] = mapped_column(String(20))
    color: Mapped[str] = mapped_column(String(40))
    stock: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped[Product] = relationship(back_populates="variants")

    @property
    def available(self) -> bool:
        return self.stock > 0
