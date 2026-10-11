from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.inspiration import Inspiration


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Se guarda en minúsculas: el correo es único sin importar mayúsculas.
    email: Mapped[str] = mapped_column(String(254), unique=True)
    # deferred: no se lee de la base salvo que se pida (como `select: false`).
    password_hash: Mapped[str] = mapped_column(String(255), deferred=True)
    name: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    inspirations: Mapped[list["Inspiration"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )
