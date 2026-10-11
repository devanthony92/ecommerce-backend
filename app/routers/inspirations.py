from collections.abc import Sequence

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.dependencies import CurrentUser, DbSession
from app.errors import AppError, conflict, forbidden, not_found
from app.models import Inspiration
from app.schemas.inspiration import InspirationIn, InspirationOut

router = APIRouter(prefix="/inspirations", tags=["inspirations"])


def _already_saved() -> AppError:
    return conflict("ALREADY_SAVED", "Ya guardaste esta foto.")


@router.get("", response_model=list[InspirationOut])
def list_inspirations(user: CurrentUser, db: DbSession) -> Sequence[Inspiration]:
    """Solo las del usuario conectado, de la más reciente a la más antigua."""
    return db.scalars(
        select(Inspiration)
        .where(Inspiration.owner_id == user.id)
        .order_by(Inspiration.created_at.desc(), Inspiration.id.desc())
    ).all()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=InspirationOut)
def create_inspiration(data: InspirationIn, user: CurrentUser, db: DbSession) -> Inspiration:
    exists = db.scalar(
        select(Inspiration.id).where(
            Inspiration.owner_id == user.id, Inspiration.photo_id == data.photo_id
        )
    )
    if exists is not None:
        raise _already_saved()

    inspiration = Inspiration(**data.model_dump(mode="json"), owner_id=user.id)
    db.add(inspiration)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _already_saved() from None
    db.refresh(inspiration)
    return inspiration


@router.delete("/{inspiration_id}", response_model=InspirationOut)
def delete_inspiration(inspiration_id: int, user: CurrentUser, db: DbSession) -> Inspiration:
    inspiration = db.get(Inspiration, inspiration_id)
    if inspiration is None:
        raise not_found("La inspiración no existe.")
    # Nadie puede borrar lo que guardó otro usuario.
    if inspiration.owner_id != user.id:
        raise forbidden("No puedes borrar inspiraciones de otro usuario.")
    db.delete(inspiration)
    db.commit()
    return inspiration
