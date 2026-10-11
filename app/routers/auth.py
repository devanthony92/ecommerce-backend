from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import undefer

from app.dependencies import DbSession
from app.errors import AppError, conflict
from app.models import User
from app.schemas.user import SigninIn, SignupIn, TokenOut, UserOut
from app.security import DUMMY_HASH, create_token, hash_password, verify_password

router = APIRouter(tags=["auth"])


def _email_taken() -> AppError:
    return conflict(
        "EMAIL_TAKEN",
        "Ya existe una cuenta con ese correo.",
        {"email": "Ya existe una cuenta con ese correo. ¿Quieres ingresar?"},
    )


@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def signup(data: SignupIn, db: DbSession) -> User:
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


@router.post("/signin", response_model=TokenOut)
def signin(data: SigninIn, db: DbSession) -> dict[str, str]:
    user = db.scalar(
        select(User).options(undefer(User.password_hash)).where(User.email == data.email)
    )
    # Siempre se verifica un hash (el real o uno de relleno) para no revelar
    # por el tiempo de respuesta si el correo existe.
    valid = verify_password(data.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid:
        raise AppError(401, "INVALID_CREDENTIALS", "Correo o contraseña incorrectos.")
    return {"token": create_token(user.id)}
