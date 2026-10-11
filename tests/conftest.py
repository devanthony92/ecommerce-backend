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


@pytest.fixture(scope="session", autouse=True)
def schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        load_catalog(db)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE inspirations, users RESTART IDENTITY CASCADE"))


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
