from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WholesaleRequest(Base):
    """Solicitud de cuenta mayorista. Una por usuario: reenviarla reemplaza la anterior."""

    __tablename__ = "wholesale_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    # PENDING | UNDER_REVIEW | APPROVED | REJECTED | SUSPENDED
    status: Mapped[str] = mapped_column(String(20))
    # Datos comerciales tal como los envió (nombre del negocio, NIT, etc.).
    data: Mapped[dict] = mapped_column(JSONB)
    rejection_reason: Mapped[str | None] = mapped_column(Text, default=None)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
