from tests.conftest import PASSWORD, error_of, signup


def test_signup_crea_usuario_sin_devolver_la_contrasena(client):
    response = signup(client, email="  Laura@Trama.CO ", name="  Laura  ")

    assert response.status_code == 201
    body = response.json()
    assert body == {"id": 1, "email": "laura@trama.co", "name": "Laura"}
    assert "password" not in response.text
    assert "passwordHash" not in response.text


def test_signup_correo_repetido_responde_409(client):
    signup(client)
    response = signup(client, email="LAURA@trama.co")

    assert response.status_code == 409
    assert error_of(response)["code"] == "EMAIL_TAKEN"
    assert "email" in error_of(response)["details"]


def test_signup_valida_el_cuerpo_antes_del_controlador(client):
    response = client.post(
        "/signup", json={"email": "no-es-correo", "password": "123", "name": "L"}
    )

    assert response.status_code == 400
    error = error_of(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"] == {
        "email": "Ingresa un correo válido.",
        "password": "Mínimo 8 caracteres.",
        "name": "Debe tener al menos 2 caracteres.",
    }


def test_signup_sin_campos(client):
    response = client.post("/signup", json={})

    assert response.status_code == 400
    assert error_of(response)["details"] == {
        "email": "Campo obligatorio.",
        "password": "Campo obligatorio.",
        "name": "Campo obligatorio.",
    }


def test_signup_con_json_invalido(client):
    response = client.post(
        "/signup", content="{no es json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400


def test_signin_devuelve_un_jwt(client):
    signup(client)
    response = client.post("/signin", json={"email": "LAURA@trama.co", "password": PASSWORD})

    assert response.status_code == 200
    token = response.json()["token"]
    assert token.count(".") == 2


def test_signin_con_contrasena_incorrecta_responde_401(client):
    signup(client)
    response = client.post("/signin", json={"email": "laura@trama.co", "password": "otra-clave"})

    assert response.status_code == 401
    assert error_of(response)["code"] == "INVALID_CREDENTIALS"


def test_signin_correo_inexistente_responde_igual(client):
    response = client.post("/signin", json={"email": "nadie@trama.co", "password": PASSWORD})

    assert response.status_code == 401
    assert error_of(response)["message"] == "Correo o contraseña incorrectos."
