from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(40))
    recipient: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str] = mapped_column(String(10))
    department: Mapped[str] = mapped_column(String(40))
    city: Mapped[str] = mapped_column(String(80))
    line1: Mapped[str] = mapped_column(String(120))
    line2: Mapped[str | None] = mapped_column(String(120), default=None)
    notes: Mapped[str | None] = mapped_column(String(200), default=None)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordReset(Base):
    """Enlace de un solo uso para restablecer la contraseña.

    Se guarda el hash SHA-256 del token, nunca el token: si la base se filtra,
    los enlaces pendientes no sirven.
    """

    __tablename__ = "password_resets"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
