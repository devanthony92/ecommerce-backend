from typing import Annotated

from pydantic import AfterValidator, EmailStr, Field, StringConstraints

from app.schemas.base import CamelModel

# El correo se compara y se guarda en minúsculas.
Email = Annotated[EmailStr, AfterValidator(str.lower)]


# La contraseña nunca se recorta: se guarda tal como la escribió el usuario.
class SignupIn(CamelModel):
    email: Email
    password: str = Field(min_length=8, max_length=128)
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=30)]


class SigninIn(CamelModel):
    email: Email
    password: str = Field(min_length=1, max_length=128)


class TokenOut(CamelModel):
    token: str


class UserOut(CamelModel):
    """Datos públicos del usuario: nunca incluye la contraseña."""

    id: int
    email: str
    name: str
