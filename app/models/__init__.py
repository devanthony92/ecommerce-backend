# Importar los modelos aquí los registra en Base.metadata (Alembic y tests).
from app.models.catalog import Category, Product, ProductVariant
from app.models.inspiration import Inspiration
from app.models.user import User

__all__ = ["Category", "Inspiration", "Product", "ProductVariant", "User"]
