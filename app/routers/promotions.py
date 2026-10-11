from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from app.constants import PROMOTIONS

router = APIRouter(prefix="/promotions", tags=["promotions"])


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


@router.get("/active")
def active_promotions() -> list[dict[str, Any]]:
    """Promociones vigentes hoy (entre su inicio y su fin)."""
    now = datetime.now(UTC)
    return [
        promotion
        for promotion in PROMOTIONS
        if _parse(promotion["startsAt"]) <= now <= _parse(promotion["endsAt"])
    ]
