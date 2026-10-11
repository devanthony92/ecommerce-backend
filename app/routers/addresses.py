from typing import Annotated, Any

from fastapi import APIRouter, Response, status
from pydantic import AfterValidator, BeforeValidator, StringConstraints
from sqlalchemy import select, update

from app.constants import DEPARTMENTS, PHONE_RE
from app.dependencies import CurrentUser, DbSession
from app.errors import not_found, validate_payload
from app.models import Address
from app.schemas.base import CamelModel

router = APIRouter(prefix="/users/me/addresses", tags=["addresses"])


def _text(max_length: int, min_length: int = 1):
    return Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)
    ]


def _optional(value: Any) -> Any:
    return (value.strip() or None) if isinstance(value, str) else value


def _check_phone(phone: str) -> str:
    if not PHONE_RE.match(phone):
        raise ValueError("Celular de 10 dígitos que empiece por 3.")
    return phone


def _check_department(department: str) -> str:
    if department not in DEPARTMENTS:
        raise ValueError("Elige un departamento.")
    return department


def _optional_text(max_length: int):
    # Vacío o solo espacios se guarda como null.
    return Annotated[
        Annotated[str, StringConstraints(max_length=max_length)] | None,
        BeforeValidator(_optional),
    ]


class AddressIn(CamelModel):
    label: _text(40)
    recipient: _text(80)
    phone: Annotated[str, StringConstraints(strip_whitespace=True), AfterValidator(_check_phone)]
    department: Annotated[str, AfterValidator(_check_department)]
    city: _text(80)
    line1: _text(120, min_length=5)
    line2: _optional_text(120) = None
    notes: _optional_text(200) = None
    is_default: bool = False


def address_json(address: Address) -> dict[str, Any]:
    return {
        "id": address.id,
        "label": address.label,
        "recipient": address.recipient,
        "phone": address.phone,
        "department": address.department,
        "city": address.city,
        "line1": address.line1,
        "line2": address.line2,
        "notes": address.notes,
        "isDefault": address.is_default,
    }


def addresses_of(db, user_id: int) -> list[Address]:
    return list(
        db.scalars(select(Address).where(Address.user_id == user_id).order_by(Address.id)).all()
    )


def _clear_default(db, user_id: int) -> None:
    db.execute(update(Address).where(Address.user_id == user_id).values(is_default=False))


@router.get("")
def list_addresses(user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    return [address_json(address) for address in addresses_of(db, user.id)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_address(data: AddressIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    # La primera dirección siempre queda como predeterminada.
    is_default = data.is_default or not addresses_of(db, user.id)
    if is_default:
        _clear_default(db, user.id)
    address = Address(**data.model_dump(exclude={"is_default"}), user_id=user.id)
    address.is_default = is_default
    db.add(address)
    db.commit()
    return address_json(address)


def _own_address(db, user_id: int, address_id: int) -> Address:
    address = db.get(Address, address_id)
    if address is None or address.user_id != user_id:
        raise not_found("La dirección no existe.")
    return address


@router.patch("/{address_id}")
def update_address(
    address_id: int, body: dict[str, Any], user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    address = _own_address(db, user.id, address_id)
    # Actualización parcial: se fusiona con lo guardado y se valida completo.
    merged = {**address_json(address), **body}
    data = validate_payload(AddressIn, merged)
    if body.get("isDefault"):
        _clear_default(db, user.id)
    for field, value in data.model_dump().items():
        setattr(address, field, value)
    db.commit()
    return address_json(address)


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(address_id: int, user: CurrentUser, db: DbSession) -> Response:
    address = db.get(Address, address_id)
    if address is not None and address.user_id == user.id:
        was_default = address.is_default
        db.delete(address)
        db.flush()
        remaining = addresses_of(db, user.id)
        # Si se borró la predeterminada, la siguiente pasa a serlo.
        if was_default and remaining:
            remaining[0].is_default = True
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
