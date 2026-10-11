# Importar los modelos aquí los registra en Base.metadata (Alembic y tests).
from app.models.account import Address, PasswordReset
from app.models.catalog import Category, Product, ProductVariant
from app.models.commerce import CartItem, Order, OrderItem
from app.models.inspiration import Inspiration
from app.models.user import User

__all__ = [
    "Address",
    "CartItem",
    "Category",
    "Inspiration",
    "Order",
    "OrderItem",
    "PasswordReset",
    "Product",
    "ProductVariant",
    "User",
]
