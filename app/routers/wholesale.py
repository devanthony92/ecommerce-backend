from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, status
from pydantic import AfterValidator, Field, StringConstraints
from sqlalchemy import func, select

from app.config import get_settings
from app.constants import (
    BUSINESS_TYPES,
    MONTHLY_VOLUMES,
    NIT_RE,
    PHONE_RE,
    REVIEW_STATUSES,
    WHOLESALE_BENEFITS,
    WHOLESALE_MINIMUM_ORDER,
)
from app.dependencies import CurrentUser, DbSession
from app.errors import AppError, conflict, forbidden
from app.models import Category, Order, OrderItem, ProductVariant, User, WholesaleRequest
from app.schemas.base import CamelModel
from app.services.catalog import image_for_color
from app.services.pricing import build_price_view, round_half_up

router = APIRouter(prefix="/wholesale", tags=["wholesale"])

Json = dict[str, Any]


def _only_wholesale(user: User) -> None:
    if user.role != "WHOLESALE":
        raise forbidden("Esta sección es solo para cuentas mayoristas.")


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def request_json(request: WholesaleRequest | None) -> Json | None:
    if request is None:
        return None
    return {
        "id": request.id,
        "status": request.status,
        "submittedAt": _iso(request.submitted_at),
        "reviewedAt": _iso(request.reviewed_at),
        "rejectionReason": request.rejection_reason,
        "data": request.data,
    }


# --- Programa y panel ------------------------------------------------------------


@router.get("/program")
def get_program() -> Json:
    """Condiciones del programa (público: lo muestra la página de mayoristas)."""
    return {"minimumOrder": WHOLESALE_MINIMUM_ORDER, "benefits": list(WHOLESALE_BENEFITS)}


@router.get("/profile")
def get_profile(user: CurrentUser, db: DbSession) -> Json:
    _only_wholesale(user)
    year = datetime.now(UTC).year
    start = datetime(year, 1, 1, tzinfo=UTC)
    # Compras del año, sin contar los pedidos cancelados.
    accumulated, savings = db.execute(
        select(
            func.coalesce(func.sum(Order.total), 0),
            func.coalesce(func.sum(Order.discount_total), 0),
        ).where(Order.user_id == user.id, Order.status != "CANCELLED", Order.created_at >= start)
    ).one()
    return {
        "accumulatedPurchase": accumulated,
        "period": {"from": f"{year}-01-01", "to": f"{year}-12-31"},
        "totalSavings": savings,
        "minimumOrder": WHOLESALE_MINIMUM_ORDER,
        "benefits": list(WHOLESALE_BENEFITS),
    }


@router.get("/frequent-products")
def get_frequent_products(user: CurrentUser, db: DbSession) -> list[Json]:
    """Variantes que más compra, con su cantidad habitual (promedio por pedido)."""
    _only_wholesale(user)
    rows = db.execute(
        select(
            OrderItem.variant_id,
            func.count(func.distinct(OrderItem.order_id)),
            func.sum(OrderItem.quantity),
            func.max(Order.created_at),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.user_id == user.id, Order.status != "CANCELLED")
        .group_by(OrderItem.variant_id)
    ).all()

    items = []
    for variant_id, times, units, last in rows:
        variant = db.get(ProductVariant, variant_id)
        if variant is None:
            continue
        product = variant.product
        usual = max(1, round_half_up(units / times))
        image = image_for_color(product, variant.color)
        items.append(
            {
                "variant": {
                    "id": variant.id,
                    "sku": variant.sku,
                    "attributes": {"size": variant.size, "color": variant.color},
                    "available": variant.available,
                    "stock": variant.stock,
                },
                "product": {
                    "slug": product.slug,
                    "name": product.name,
                    "image": {"url": image["url"], "alt": image["alt"]},
                },
                "usualQuantity": usual,
                "timesOrdered": times,
                "lastOrderedAt": _iso(last),
                "pricing": build_price_view(product, user, usual),
            }
        )
    # Más pedidas primero; a igual número de pedidos, la más reciente.
    items.sort(key=lambda item: item["lastOrderedAt"], reverse=True)
    items.sort(key=lambda item: item["timesOrdered"], reverse=True)
    return items


# --- Solicitud -------------------------------------------------------------------

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


def _check(regex, message: str):
    def check(value: str) -> str:
        if not regex.match(value):
            raise ValueError(message)
        return value

    return AfterValidator(check)


def _one_of(options: tuple[str, ...], message: str):
    def check(value: str) -> str:
        if value not in options:
            raise ValueError(message)
        return value

    return AfterValidator(check)


class WholesaleRequestIn(CamelModel):
    trade_name: Text
    legal_name: Text
    nit: Annotated[
        str,
        StringConstraints(strip_whitespace=True),
        _check(NIT_RE, "NIT o cédula sin puntos (ej. 900123456-7)."),
    ]
    phone: Annotated[
        str,
        StringConstraints(strip_whitespace=True),
        _check(PHONE_RE, "Celular de 10 dígitos que empiece por 3."),
    ]
    city: Text
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=160)]
    business_type: Annotated[str, _one_of(BUSINESS_TYPES, "Elige el tipo de negocio.")]
    social_links: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None
    ) = None
    estimated_monthly_volume: Annotated[str, _one_of(MONTHLY_VOLUMES, "Elige un volumen estimado.")]
    categories_of_interest: list[str] = Field(default_factory=list, max_length=20)


@router.get("/requests/me")
def get_my_request(user: CurrentUser, db: DbSession) -> Json | None:
    return request_json(
        db.scalar(select(WholesaleRequest).where(WholesaleRequest.user_id == user.id))
    )


@router.post("/requests", status_code=status.HTTP_201_CREATED)
def submit_request(data: WholesaleRequestIn, user: CurrentUser, db: DbSession) -> Json:
    # Puede solicitar quien nunca lo hizo o fue rechazado (mismo criterio que el permiso).
    if user.wholesale_status not in (None, "REJECTED"):
        raise conflict("REQUEST_NOT_ALLOWED", "Ya tienes una solicitud o una cuenta mayorista.")

    known = set(db.scalars(select(Category.id)).all())
    categories = [category for category in data.categories_of_interest if category in known]
    if not categories:
        message = "Elige al menos una categoría."
        raise AppError(
            400,
            "VALIDATION_ERROR",
            "Revisa los datos de la solicitud.",
            {"categoriesOfInterest": message},
        )

    payload = data.model_dump(by_alias=True)
    payload["socialLinks"] = data.social_links or None
    payload["categoriesOfInterest"] = categories

    request = db.scalar(select(WholesaleRequest).where(WholesaleRequest.user_id == user.id))
    if request is None:
        request = WholesaleRequest(user_id=user.id)
        db.add(request)
    request.status = "PENDING"
    request.data = payload
    request.rejection_reason = None
    request.submitted_at = datetime.now(UTC)
    request.reviewed_at = None
    user.wholesale_status = "PENDING"
    db.commit()
    return request_json(request)


class ReviewIn(CamelModel):
    status: Annotated[str, _one_of(REVIEW_STATUSES, "Estado no válido.")]
    rejection_reason: str | None = Field(default=None, max_length=300)


# SOLO DESARROLLO: simula la decisión del administrador (en producción no existe;
# la decidirá el panel administrativo).
dev_router = APIRouter(prefix="/_dev", tags=["dev"])


@dev_router.post("/wholesale-review")
def simulate_review(data: ReviewIn, user: CurrentUser, db: DbSession) -> Json:
    if get_settings().is_production:
        raise AppError(404, "NOT_FOUND", "El recurso solicitado no existe.")
    request = db.scalar(select(WholesaleRequest).where(WholesaleRequest.user_id == user.id))
    if request is None:
        raise AppError(404, "REQUEST_NOT_FOUND", "No hay solicitud para revisar.")

    request.status = data.status
    request.reviewed_at = None if data.status == "UNDER_REVIEW" else datetime.now(UTC)
    request.rejection_reason = (
        data.rejection_reason or "No pudimos verificar el NIT del negocio."
        if data.status == "REJECTED"
        else None
    )
    user.wholesale_status = data.status
    user.role = "WHOLESALE" if data.status == "APPROVED" else "BUYER"
    db.commit()
    return {"request": request_json(request)}
