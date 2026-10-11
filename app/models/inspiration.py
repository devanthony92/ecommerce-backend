from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User

URL_LENGTH = 2048


class Inspiration(Base):
    """Foto de Unsplash que un usuario guardó desde la página Inspiración."""

    __tablename__ = "inspirations"
    __table_args__ = (
        UniqueConstraint("owner_id", "photo_id", name="uq_inspirations_owner_photo_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Palabra con la que se encontró la foto.
    keyword: Mapped[str] = mapped_column(String(100))
    # Id de la foto en Unsplash (texto, p. ej. "Dwu85P9SOIk").
    photo_id: Mapped[str] = mapped_column(String(64))
    alt: Mapped[str] = mapped_column(String(500), default="")
    photographer: Mapped[str] = mapped_column(String(200))
    photographer_url: Mapped[str] = mapped_column(String(URL_LENGTH))
    link: Mapped[str] = mapped_column(String(URL_LENGTH))
    image: Mapped[str] = mapped_column(String(URL_LENGTH))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["User"] = relationship(back_populates="inspirations")
