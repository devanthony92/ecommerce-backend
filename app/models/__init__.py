# Importar los modelos aquí los registra en Base.metadata (Alembic y tests).
from app.models.inspiration import Inspiration
from app.models.user import User

__all__ = ["Inspiration", "User"]
