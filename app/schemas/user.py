from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator, EmailStr, Field, StringConstraints

from app.constants import BASE_PERMISSIONS, PHONE_RE
from app.models import User
from app.schemas.base import CamelModel

# El correo se compara y se guarda en minúsculas.
Email = Annotated[EmailStr, AfterValidator(str.lower)]

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=30)]


def _check_password(password: str) -> str:
    # Misma regla que el frontend: mínimo 8 caracteres, con letras y números.
    if len(password) < 8:
        raise ValueError("Mínimo 8 caracteres.")
    if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        raise ValueError("Usa letras y números.")
    return password


# La contraseña nunca se recorta: se guarda tal como la escribió el usuario.
NewPassword = Annotated[str, Field(max_length=128), AfterValidator(_check_password)]


def _empty_to_none(value: Any) -> Any:
    return value.strip() or None if isinstance(value, str) else value


def _check_phone(phone: str | None) -> str | None:
    if phone is not None and not PHONE_RE.match(phone):
        raise ValueError("Celular de 10 dígitos que empiece por 3.")
    return phone


Phone = Annotated[str | None, BeforeValidator(_empty_to_none), AfterValidator(_check_phone)]


class SignupIn(CamelModel):
    email: Email
    password: NewPassword
    name: Name


def _check_terms(accepted: bool) -> bool:
    if not accepted:
        raise ValueError("Debes aceptar los términos para crear la cuenta.")
    return accepted


class RegisterIn(SignupIn):
    """Registro de la tienda: además exige aceptar los términos y devuelve sesión."""

    accept_terms: Annotated[bool, AfterValidator(_check_terms)] = Field(
        default=False, validate_default=True
    )


class SigninIn(CamelModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class TokenOut(CamelModel):
    token: str


class UserOut(CamelModel):
    """Respuesta de /signup: datos públicos básicos, nunca la contraseña."""

    id: int
    email: str
    name: str


class ProfileIn(CamelModel):
    name: Name | None = None
    phone: Phone = None


class PasswordChangeIn(CamelModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: NewPassword


class ForgotPasswordIn(CamelModel):
    email: Email


class ResetPasswordIn(CamelModel):
    token: str = Field(min_length=1, max_length=200)
    password: NewPassword


def permissions_for(user: User) -> list[str]:
    """Lo que la interfaz puede ofrecer. El backend igual valida cada acción."""
    if user.role == "WHOLESALE":
        return [*BASE_PERMISSIONS, "wholesale.access", "wholesale.quick-order"]
    if user.role == "ADMIN":
        return [*BASE_PERMISSIONS, "admin.access"]
    # Puede solicitar si nunca lo hizo o si fue rechazado. Suspendido debe contactar a la tienda.
    if user.wholesale_status in (None, "REJECTED"):
        return [*BASE_PERMISSIONS, "wholesale.request"]
    return list(BASE_PERMISSIONS)


def user_json(user: User) -> dict[str, Any]:
    """Usuario público (contrato §7 del frontend). Nunca incluye la contraseña."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "phone": user.phone,
        "role": user.role,
        "wholesale": {"requestStatus": user.wholesale_status},
        "permissions": permissions_for(user),
    }
