from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession
from app.errors import AppError
from app.models import User
from app.schemas.user import PasswordChangeIn, ProfileIn, user_json
from app.security import hash_password, verify_password

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def read_me(user: CurrentUser) -> dict[str, Any]:
    """Correo y nombre del usuario conectado, más rol y permisos para la tienda."""
    return user_json(user)


@router.patch("/me")
def update_me(data: ProfileIn, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    if data.name is not None:
        user.name = data.name
    user.phone = data.phone
    db.commit()
    return user_json(user)


@router.post("/me/password")
def change_password(data: PasswordChangeIn, user: CurrentUser, db: DbSession) -> dict[str, str]:
    current_hash = db.scalar(select(User.password_hash).where(User.id == user.id))
    if not verify_password(data.current_password, current_hash):
        raise AppError(
            400,
            "INVALID_PASSWORD",
            "La contraseña actual no es correcta.",
            {"currentPassword": "La contraseña actual no es correcta."},
        )
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "Tu contraseña se actualizó."}
