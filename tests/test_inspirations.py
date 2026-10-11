import pytest

from tests.conftest import auth_headers, error_of

PHOTO = {
    "keyword": "denim",
    "pexelsId": 1043474,
    "alt": "Persona con chaqueta de jean",
    "photographer": "Daniel Xavier",
    "photographerUrl": "https://www.pexels.com/@danxavier",
    "link": "https://www.pexels.com/photo/1043474/",
    "image": "https://images.pexels.com/photos/1043474/portrait.jpeg",
}


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/inspirations"), ("post", "/inspirations"), ("delete", "/inspirations/1")],
)
def test_rutas_protegidas_sin_token_responden_401(client, method, path):
    response = client.request(method.upper(), path, json=PHOTO if method == "post" else None)
    assert response.status_code == 401


def test_crea_y_lista_sin_exponer_el_dueno(client):
    headers = auth_headers(client)
    created = client.post("/inspirations", json=PHOTO, headers=headers)

    assert created.status_code == 201
    body = created.json()
    assert body["pexelsId"] == PHOTO["pexelsId"]
    assert body["photographerUrl"] == PHOTO["photographerUrl"]
    assert "createdAt" in body
    assert "owner" not in created.text
    assert "ownerId" not in created.text

    listed = client.get("/inspirations", headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]


def test_cada_usuario_ve_solo_lo_suyo(client):
    laura = auth_headers(client, "laura@trama.co")
    carlos = auth_headers(client, "carlos@trama.co")
    client.post("/inspirations", json=PHOTO, headers=laura)

    assert client.get("/inspirations", headers=carlos).json() == []


def test_lista_de_la_mas_reciente_a_la_mas_antigua(client):
    headers = auth_headers(client)
    for pexels_id in (1, 2, 3):
        client.post("/inspirations", json={**PHOTO, "pexelsId": pexels_id}, headers=headers)

    ids = [item["pexelsId"] for item in client.get("/inspirations", headers=headers).json()]
    assert ids == [3, 2, 1]


def test_guardar_la_misma_foto_dos_veces_responde_409(client):
    headers = auth_headers(client)
    client.post("/inspirations", json=PHOTO, headers=headers)
    response = client.post("/inspirations", json=PHOTO, headers=headers)

    assert response.status_code == 409
    assert error_of(response)["code"] == "ALREADY_SAVED"


def test_valida_urls_y_campos_obligatorios(client):
    headers = auth_headers(client)
    response = client.post(
        "/inspirations",
        json={**PHOTO, "image": "javascript:alert(1)", "keyword": "", "pexelsId": 0},
        headers=headers,
    )

    assert response.status_code == 400
    details = error_of(response)["details"]
    assert details["image"] == "Debe ser una URL válida (http o https)."
    assert details["keyword"] == "Campo obligatorio."
    assert details["pexelsId"] == "Debe ser mayor que 0."


def test_borra_la_propia_y_luego_no_existe(client):
    headers = auth_headers(client)
    created = client.post("/inspirations", json=PHOTO, headers=headers).json()

    deleted = client.delete(f"/inspirations/{created['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["id"] == created["id"]

    again = client.delete(f"/inspirations/{created['id']}", headers=headers)
    assert again.status_code == 404
    assert client.get("/inspirations", headers=headers).json() == []


def test_no_puede_borrar_la_de_otro_usuario(client):
    laura = auth_headers(client, "laura@trama.co")
    carlos = auth_headers(client, "carlos@trama.co")
    created = client.post("/inspirations", json=PHOTO, headers=laura).json()

    response = client.delete(f"/inspirations/{created['id']}", headers=carlos)
    assert response.status_code == 403
    assert error_of(response)["code"] == "FORBIDDEN"
    assert len(client.get("/inspirations", headers=laura).json()) == 1


def test_id_no_numerico_responde_400(client):
    headers = auth_headers(client)
    response = client.delete("/inspirations/abc", headers=headers)

    assert response.status_code == 400
    assert error_of(response)["details"] == {"inspiration_id": "Debe ser un número entero."}
