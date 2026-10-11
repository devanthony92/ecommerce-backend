import os
import tempfile

# Antes de importar la app: base de pruebas y logs en una carpeta temporal.
os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://trama:trama_dev@localhost:5432/trama_test"
)
os.environ["LOG_DIR"] = tempfile.mkdtemp(prefix="trama-logs-")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import Base, engine
from app.main import app
from app.seed import load_catalog

PASSWORD = "Trama1234"


# Tablas con datos de cada test (el catálogo se carga una vez por sesión).
USER_TABLES = (
    "shopping_list_items, shopping_lists, favorites, wholesale_requests, order_items, orders, "
    "cart_items, password_resets, addresses, inspirations, users"
)


@pytest.fixture(scope="session", autouse=True)
def schema():
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS _stock_snapshot"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        load_catalog(db)
    # Copia del stock inicial: los pedidos lo descuentan y cada test lo restaura.
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE _stock_snapshot AS SELECT id, stock FROM product_variants")
        )
    yield
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS _stock_snapshot"))
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {USER_TABLES} RESTART IDENTITY CASCADE"))
        connection.execute(
            text(
                "UPDATE product_variants AS v SET stock = s.stock FROM _stock_snapshot AS s "
                "WHERE v.id = s.id AND v.stock <> s.stock"
            )
        )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def signup(client: TestClient, email: str = "laura@trama.co", name: str = "Laura"):
    return client.post("/signup", json={"email": email, "password": PASSWORD, "name": name})


def auth_headers(client: TestClient, email: str = "laura@trama.co") -> dict[str, str]:
    signup(client, email=email)
    token = client.post("/signin", json={"email": email, "password": PASSWORD}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def error_of(response) -> dict:
    return response.json()["error"]


def wholesale_headers(client: TestClient, email: str = "tienda@trama.co") -> dict[str, str]:
    """Sesión de una cuenta mayorista (aprobada directamente en la base)."""
    headers = auth_headers(client, email)
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE users SET role = 'WHOLESALE', wholesale_status = 'APPROVED' "
                "WHERE email = :email"
            ),
            {"email": email},
        )
    return headers


ADDRESS = {
    "label": "Casa",
    "recipient": "Laura Gómez",
    "phone": "3001112233",
    "department": "Antioquia",
    "city": "Medellín",
    "line1": "Calle 10 # 20-30",
}


def create_address(client: TestClient, headers: dict[str, str], **changes) -> dict:
    return client.post("/users/me/addresses", json={**ADDRESS, **changes}, headers=headers).json()
