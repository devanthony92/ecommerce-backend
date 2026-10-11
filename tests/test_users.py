from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings
from tests.conftest import auth_headers, error_of


def test_me_devuelve_correo_y_nombre(client):
    headers = auth_headers(client)
    response = client.get("/users/me", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"id": 1, "email": "laura@trama.co", "name": "Laura"}


def test_me_sin_token_responde_401(client):
    response = client.get("/users/me")

    assert response.status_code == 401
    assert error_of(response)["code"] == "UNAUTHORIZED"


def test_me_con_token_invalido_responde_401(client):
    response = client.get("/users/me", headers={"Authorization": "Bearer no.es.jwt"})
    assert response.status_code == 401


def test_me_con_token_expirado_responde_401(client):
    auth_headers(client)
    expired = jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    response = client.get("/users/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_me_con_token_firmado_con_otra_clave_responde_401(client):
    auth_headers(client)
    forged = jwt.encode(
        {"sub": "1", "exp": datetime.now(UTC) + timedelta(days=1)},
        "otra-clave-que-no-es-la-del-servidor-32b",
        algorithm="HS256",
    )
    response = client.get("/users/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
