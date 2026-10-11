import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, undefer

from app.config import get_settings
from app.dependencies import DbSession
from app.errors import AppError, conflict
from app.models import PasswordReset, User
from app.schemas.user import (
    ForgotPasswordIn,
    RegisterIn,
    ResetPasswordIn,
    SigninIn,
    SignupIn,
    TokenOut,
    UserOut,
    user_json,
)
from app.security import DUMMY_HASH, create_token, hash_password, verify_password

router = APIRouter(tags=["auth"])

RESET_TTL = timedelta(minutes=30)


def _email_taken() -> AppError:
    return conflict(
        "EMAIL_TAKEN",
        "Ya existe una cuenta con ese correo.",
        {"email": "Ya existe una cuenta con ese correo. ¿Quieres ingresar?"},
    )


def _create_user(db: Session, data: SignupIn) -> User:
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise _email_taken()
    user = User(email=data.email, name=data.name, password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Dos registros simultáneos con el mismo correo: gana el índice único.
        db.rollback()
        raise _email_taken() from None
    return user


def _authenticate(db: Session, data: SigninIn) -> User:
    user = db.scalar(
        select(User).options(undefer(User.password_hash)).where(User.email == data.email)
    )
    # Siempre se verifica un hash (el real o uno de relleno) para no revelar
    # por el tiempo de respuesta si el correo existe.
    valid = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid:
        raise AppError(401, "INVALID_CREDENTIALS", "Correo o contraseña incorrectos.")
    return user


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- Rutas pedidas por TripleTen -------------------------------------------------


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def signup(data: SignupIn, db: DbSession) -> User:
    return _create_user(db, data)


@router.post("/signin", response_model=TokenOut)
def signin(data: SigninIn, db: DbSession) -> dict[str, str]:
    return {"token": create_token(_authenticate(db, data).id)}


# --- Rutas de la tienda (devuelven también el usuario) ---------------------------


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(data: RegisterIn, db: DbSession) -> dict[str, Any]:
    user = _create_user(db, data)
    return {"token": create_token(user.id), "user": user_json(user)}


@router.post("/auth/login")
def login(data: SigninIn, db: DbSession) -> dict[str, Any]:
    user = _authenticate(db, data)
    return {"token": create_token(user.id), "user": user_json(user)}


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> Response:
    # Los JWT no se guardan en el servidor: cerrar sesión es borrar el token en el cliente.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/auth/password/forgot")
def forgot_password(data: ForgotPasswordIn, db: DbSession) -> dict[str, str]:
    # Respuesta idéntica exista o no la cuenta: no revela qué correos están registrados.
    response = {
        "message": "Si el correo está registrado, te enviamos un enlace para restablecer "
        "la contraseña."
    }
    user = db.scalar(select(User).where(User.email == data.email))
    if user is None:
        return response

    token = secrets.token_urlsafe(32)
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    db.add(
        PasswordReset(
            token_hash=_hash_token(token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + RESET_TTL,
        )
    )
    db.commit()
    # Todavía no hay envío de correos: fuera de producción el enlace se devuelve
    # para poder probar el flujo. En producción NUNCA se expone.
    if not get_settings().is_production:
        response["devResetToken"] = token
    return response


@router.post("/auth/password/reset")
def reset_password(data: ResetPasswordIn, db: DbSession) -> dict[str, str]:
    reset = db.get(PasswordReset, _hash_token(data.token))
    if reset is None or reset.expires_at < datetime.now(UTC):
        raise AppError(
            400, "RESET_TOKEN_INVALID", "El enlace venció o ya se usó. Solicita uno nuevo."
        )
    user = db.get(User, reset.user_id)
    user.password_hash = hash_password(data.password)
    db.delete(reset)
    db.commit()
    return {"message": "Tu contraseña se actualizó. Ya puedes ingresar."}
