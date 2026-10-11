from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import unauthorized
from app.models import User
from app.security import decode_token

# auto_error=False: la falta de token la responde nuestro handler (401 con el formato común).
_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Protege una ruta: exige `Authorization: Bearer <JWT>` válido."""
    if credentials is None:
        raise unauthorized()
    user_id = decode_token(credentials.credentials)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_optional_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User | None:
    """Rutas públicas cuyo resultado depende de quién mira (p. ej. precios).

    Sin token o con token no válido responde como visitante: nunca 401.
    """
    if credentials is None:
        return None
    user_id = decode_token(credentials.credentials)
    return db.get(User, user_id) if user_id is not None else None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
