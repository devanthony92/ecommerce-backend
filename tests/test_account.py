from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.database import engine
from app.models import PasswordReset
from tests.conftest import PASSWORD, auth_headers, error_of

REGISTER = {
    "name": "Laura Gómez",
    "email": "laura@trama.co",
    "password": PASSWORD,
    "acceptTerms": True,
}

ADDRESS = {
    "label": "Casa",
    "recipient": "Laura Gómez",
    "phone": "3001112233",
    "department": "Antioquia",
    "city": "Medellín",
    "line1": "Calle 10 # 20-30",
}


# --- Registro e ingreso de la tienda ---------------------------------------------


def test_registro_devuelve_token_y_usuario_con_permisos(client):
    response = client.post("/auth/register", json=REGISTER)

    assert response.status_code == 201
    body = response.json()
    assert body["token"].count(".") == 2
    assert body["user"] == {
        "id": 1,
        "email": "laura@trama.co",
        "name": "Laura Gómez",
        "phone": None,
        "role": "BUYER",
        "wholesale": {"requestStatus": None},
        "permissions": [
            "cart.manage",
            "checkout.create",
            "orders.view",
            "favorites.manage",
            "lists.manage",
            "wholesale.request",
        ],
    }


def test_registro_exige_terminos_y_contrasena_con_letras_y_numeros(client):
    response = client.post(
        "/auth/register", json={**REGISTER, "password": "solotexto", "acceptTerms": False}
    )

    assert response.status_code == 400
    assert error_of(response)["details"] == {
        "password": "Usa letras y números.",
        "acceptTerms": "Debes aceptar los términos para crear la cuenta.",
    }


def test_registro_sin_aceptar_terminos_explicitamente(client):
    body = {key: value for key, value in REGISTER.items() if key != "acceptTerms"}
    response = client.post("/auth/register", json=body)

    assert error_of(response)["details"] == {
        "acceptTerms": "Debes aceptar los términos para crear la cuenta."
    }


def test_login_devuelve_token_y_usuario(client):
    client.post("/auth/register", json=REGISTER)
    response = client.post("/auth/login", json={"email": "LAURA@trama.co", "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "laura@trama.co"


def test_logout(client):
    assert client.post("/auth/logout").status_code == 204


# --- Perfil ----------------------------------------------------------------------


def test_actualiza_nombre_y_celular(client):
    headers = auth_headers(client)
    response = client.patch(
        "/users/me", json={"name": "  Laura G.  ", "phone": "3005556677"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Laura G."
    assert response.json()["phone"] == "3005556677"

    cleared = client.patch("/users/me", json={"phone": ""}, headers=headers).json()
    assert cleared["phone"] is None
    assert cleared["name"] == "Laura G."


def test_celular_no_valido(client):
    headers = auth_headers(client)
    response = client.patch("/users/me", json={"phone": "12345"}, headers=headers)

    assert response.status_code == 400
    assert error_of(response)["details"] == {"phone": "Celular de 10 dígitos que empiece por 3."}


def test_cambia_la_contrasena(client):
    headers = auth_headers(client)

    wrong = client.post(
        "/users/me/password",
        json={"currentPassword": "otra", "newPassword": "Nueva1234"},
        headers=headers,
    )
    assert wrong.status_code == 400
    assert error_of(wrong)["details"] == {"currentPassword": "La contraseña actual no es correcta."}

    ok = client.post(
        "/users/me/password",
        json={"currentPassword": PASSWORD, "newPassword": "Nueva1234"},
        headers=headers,
    )
    assert ok.status_code == 200
    login = client.post("/signin", json={"email": "laura@trama.co", "password": "Nueva1234"})
    assert login.status_code == 200


# --- Recuperación de contraseña --------------------------------------------------


def test_recuperar_y_restablecer_la_contrasena(client):
    client.post("/auth/register", json=REGISTER)
    forgot = client.post("/auth/password/forgot", json={"email": "laura@trama.co"}).json()

    token = forgot["devResetToken"]
    reset = client.post("/auth/password/reset", json={"token": token, "password": "Nueva1234"})
    assert reset.status_code == 200

    # El enlace es de un solo uso.
    again = client.post("/auth/password/reset", json={"token": token, "password": "Otra12345"})
    assert error_of(again)["code"] == "RESET_TOKEN_INVALID"
    assert (
        client.post(
            "/auth/login", json={"email": "laura@trama.co", "password": "Nueva1234"}
        ).status_code
        == 200
    )


def test_recuperar_no_revela_si_el_correo_existe(client):
    response = client.post("/auth/password/forgot", json={"email": "nadie@trama.co"})

    assert response.status_code == 200
    assert "devResetToken" not in response.json()


def test_enlace_vencido(client):
    client.post("/auth/register", json=REGISTER)
    token = client.post("/auth/password/forgot", json={"email": "laura@trama.co"}).json()[
        "devResetToken"
    ]
    with engine.begin() as connection:
        connection.execute(
            update(PasswordReset).values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )

    response = client.post("/auth/password/reset", json={"token": token, "password": "Nueva1234"})
    assert error_of(response)["code"] == "RESET_TOKEN_INVALID"


# --- Direcciones -----------------------------------------------------------------


def test_la_primera_direccion_queda_predeterminada(client):
    headers = auth_headers(client)
    first = client.post("/users/me/addresses", json=ADDRESS, headers=headers)

    assert first.status_code == 201
    assert first.json()["isDefault"] is True
    assert first.json()["line2"] is None

    second = client.post(
        "/users/me/addresses", json={**ADDRESS, "label": "Tienda", "line2": "  "}, headers=headers
    ).json()
    assert second["isDefault"] is False


def test_cambiar_la_predeterminada(client):
    headers = auth_headers(client)
    client.post("/users/me/addresses", json=ADDRESS, headers=headers)
    second = client.post(
        "/users/me/addresses", json={**ADDRESS, "label": "Tienda"}, headers=headers
    ).json()

    client.patch(f"/users/me/addresses/{second['id']}", json={"isDefault": True}, headers=headers)
    addresses = client.get("/users/me/addresses", headers=headers).json()

    assert [address["isDefault"] for address in addresses] == [False, True]
    assert addresses[1]["label"] == "Tienda"


def test_editar_valida_el_resultado_completo(client):
    headers = auth_headers(client)
    address = client.post("/users/me/addresses", json=ADDRESS, headers=headers).json()

    response = client.patch(
        f"/users/me/addresses/{address['id']}",
        json={"department": "Narnia", "line1": "x"},
        headers=headers,
    )
    assert response.status_code == 400
    assert error_of(response)["details"] == {
        "department": "Elige un departamento.",
        "line1": "Debe tener al menos 5 caracteres.",
    }


def test_borrar_la_predeterminada_promueve_la_siguiente(client):
    headers = auth_headers(client)
    first = client.post("/users/me/addresses", json=ADDRESS, headers=headers).json()
    client.post("/users/me/addresses", json={**ADDRESS, "label": "Tienda"}, headers=headers)

    assert client.delete(f"/users/me/addresses/{first['id']}", headers=headers).status_code == 204
    remaining = client.get("/users/me/addresses", headers=headers).json()
    assert [(address["label"], address["isDefault"]) for address in remaining] == [("Tienda", True)]


def test_no_puede_ver_ni_editar_direcciones_de_otro(client):
    laura = auth_headers(client, "laura@trama.co")
    carlos = auth_headers(client, "carlos@trama.co")
    address = client.post("/users/me/addresses", json=ADDRESS, headers=laura).json()

    assert client.get("/users/me/addresses", headers=carlos).json() == []
    response = client.patch(
        f"/users/me/addresses/{address['id']}", json={"label": "Mía"}, headers=carlos
    )
    assert response.status_code == 404
    client.delete(f"/users/me/addresses/{address['id']}", headers=carlos)
    assert len(client.get("/users/me/addresses", headers=laura).json()) == 1
