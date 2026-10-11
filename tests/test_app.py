import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from tests.conftest import error_of

LOG_DIR = Path(os.environ["LOG_DIR"])


def read_log(name: str) -> list[dict]:
    return [json.loads(line) for line in (LOG_DIR / name).read_text("utf-8").splitlines()]


def test_ruta_inexistente_responde_404_con_formato_comun(client):
    response = client.get("/no-existe")

    assert response.status_code == 404
    assert error_of(response) == {
        "code": "NOT_FOUND",
        "message": "El recurso solicitado no existe.",
        "details": None,
    }


def test_registra_solicitudes_y_errores_en_json(client):
    client.get("/health")
    client.get("/users/me")

    requests = read_log("request.log")
    assert {"method": "GET", "path": "/health", "status": 200}.items() <= requests[-2].items()
    assert requests[-1]["path"] == "/users/me"
    assert requests[-1]["status"] == 401
    assert "time" in requests[-1]

    errors = read_log("error.log")
    assert errors[-1]["code"] == "UNAUTHORIZED"
    assert errors[-1]["status"] == 401


def test_los_logs_no_guardan_contrasenas(client):
    client.post("/signup", json={"email": "x@trama.co", "password": "SuperSecreta99", "name": "X"})

    for name in ("request.log", "error.log"):
        assert "SuperSecreta99" not in (LOG_DIR / name).read_text("utf-8")


def test_error_no_previsto_responde_500_sin_detalles_internos():
    app = create_app()

    @app.get("/explota")
    def explota():
        raise RuntimeError("detalle interno")

    response = TestClient(app, raise_server_exceptions=False).get("/explota")

    assert response.status_code == 500
    assert error_of(response)["code"] == "INTERNAL_ERROR"
    assert "detalle interno" not in response.text
    assert "detalle interno" in (LOG_DIR / "error.log").read_text("utf-8")


def test_cors_permite_el_frontend_de_desarrollo(client):
    response = client.options(
        "/signin",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_produccion_exige_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(env="production", _env_file=None)
