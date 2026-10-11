from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


# Fechas siempre en UTC, sin importar la zona horaria del servidor de base de datos.
engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    connect_args={"options": "-c timezone=UTC"},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Una sesión por solicitud; se cierra al terminar."""
    with SessionLocal() as session:
        yield session
