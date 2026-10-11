from sqlalchemy import text

from app.database import engine
from tests.conftest import auth_headers, create_address, error_of, wholesale_headers

BLACK_M = "camiseta-basica-negro-m"
JEAN = "jean-slim-denim-30"

REQUEST = {
    "tradeName": "Moda Laura",
    "legalName": "Laura Gómez",
    "nit": "900123456-7",
    "phone": "3001112233",
    "city": "Medellín",
    "address": "Carrera 52 # 45-20",
    "businessType": "PHYSICAL_STORE",
    "socialLinks": "",
    "estimatedMonthlyVolume": "1M_5M",
    "categoriesOfInterest": ["c-camisetas", "c-inexistente"],
}


# --- Favoritos -------------------------------------------------------------------


def test_favoritos_del_mas_reciente_al_mas_antiguo(client):
    headers = auth_headers(client)
    assert client.put("/favorites/p-camiseta-basica", headers=headers).status_code == 204
    client.put("/favorites/p-jean-slim", headers=headers)
    client.put("/favorites/p-camiseta-basica", headers=headers)  # idempotente

    favorites = client.get("/favorites", headers=headers).json()
    assert [product["id"] for product in favorites] == ["p-jean-slim", "p-camiseta-basica"]
    assert favorites[0]["pricing"]["audience"] == "BUYER"

    assert client.delete("/favorites/p-jean-slim", headers=headers).status_code == 204
    assert [p["id"] for p in client.get("/favorites", headers=headers).json()] == [
        "p-camiseta-basica"
    ]


def test_favorito_de_producto_inexistente(client):
    headers = auth_headers(client)
    response = client.put("/favorites/p-no-existe", headers=headers)
    assert error_of(response)["code"] == "PRODUCT_NOT_FOUND"


# --- Listas ----------------------------------------------------------------------


def create_list(client, headers, name="Pedido mensual"):
    return client.post("/lists", json={"name": name}, headers=headers)


def test_crear_lista_y_agregar_productos(client):
    headers = auth_headers(client)
    created = create_list(client, headers)
    assert created.status_code == 201
    list_id = created.json()["id"]

    client.post(
        f"/lists/{list_id}/items", json={"variantId": BLACK_M, "quantity": 12}, headers=headers
    )
    summary = client.post(
        f"/lists/{list_id}/items", json={"variantId": BLACK_M, "quantity": 6}, headers=headers
    ).json()
    assert (summary["itemsCount"], summary["unitsCount"]) == (1, 18)
    assert summary["previews"][0]["url"].startswith("data:image/svg+xml")

    detail = client.get(f"/lists/{list_id}", headers=headers).json()
    assert detail["items"][0]["quantity"] == 18
    assert detail["items"][0]["pricing"]["quantity"] == 18


def test_nombre_de_lista_unico_sin_importar_mayusculas(client):
    headers = auth_headers(client)
    create_list(client, headers, "Pedido mensual")
    other = create_list(client, headers, "Reposición").json()

    duplicate = create_list(client, headers, "  PEDIDO MENSUAL ")
    assert duplicate.status_code == 400
    assert error_of(duplicate)["details"] == {"name": "Ya tienes una lista con ese nombre."}

    rename = client.patch(f"/lists/{other['id']}", json={"name": "pedido mensual"}, headers=headers)
    assert rename.status_code == 400
    ok = client.patch(f"/lists/{other['id']}", json={"name": "Temporada"}, headers=headers)
    assert ok.json()["name"] == "Temporada"


def test_listas_ordenadas_por_ultima_modificacion(client):
    headers = auth_headers(client)
    first = create_list(client, headers, "Primera").json()
    create_list(client, headers, "Segunda")
    client.post(
        f"/lists/{first['id']}/items", json={"variantId": BLACK_M, "quantity": 1}, headers=headers
    )

    names = [item["name"] for item in client.get("/lists", headers=headers).json()]
    assert names == ["Primera", "Segunda"]


def test_editar_y_quitar_items(client):
    headers = auth_headers(client)
    list_id = create_list(client, headers).json()["id"]
    client.post(
        f"/lists/{list_id}/items", json={"variantId": BLACK_M, "quantity": 2}, headers=headers
    )
    item = client.get(f"/lists/{list_id}", headers=headers).json()["items"][0]

    updated = client.patch(
        f"/lists/{list_id}/items/{item['id']}", json={"quantity": 24}, headers=headers
    )
    assert updated.json()["quantity"] == 24
    zero = client.patch(
        f"/lists/{list_id}/items/{item['id']}", json={"quantity": 0}, headers=headers
    )
    assert zero.status_code == 400

    assert client.delete(f"/lists/{list_id}/items/{item['id']}", headers=headers).status_code == 204
    assert client.get(f"/lists/{list_id}", headers=headers).json()["items"] == []


def test_lista_al_carrito_avisa_lo_agotado(client):
    headers = auth_headers(client)
    list_id = create_list(client, headers).json()["id"]
    for variant_id in (BLACK_M, JEAN):
        client.post(
            f"/lists/{list_id}/items",
            json={"variantId": variant_id, "quantity": 3},
            headers=headers,
        )
    with engine.begin() as connection:
        connection.execute(text(f"UPDATE product_variants SET stock = 0 WHERE id = '{JEAN}'"))

    cart = client.post(f"/lists/{list_id}/add-to-cart", headers=headers).json()
    assert [(i["variant"]["id"], i["quantity"]) for i in cart["items"]] == [(BLACK_M, 3)]
    assert cart["warnings"][0]["code"] == "LIST_ITEM_UNAVAILABLE"


def test_listas_de_otro_usuario_no_existen(client):
    laura = auth_headers(client, "laura@trama.co")
    carlos = auth_headers(client, "carlos@trama.co")
    list_id = create_list(client, laura).json()["id"]

    assert client.get(f"/lists/{list_id}", headers=carlos).status_code == 404
    client.delete(f"/lists/{list_id}", headers=carlos)
    assert client.get(f"/lists/{list_id}", headers=laura).status_code == 200


# --- Programa mayorista ----------------------------------------------------------


def test_programa_publico(client):
    program = client.get("/wholesale/program").json()
    assert program["minimumOrder"] == 120000
    assert program["benefits"][0]["code"] == "TIER_PRICES"


def test_solicitud_y_aprobacion(client):
    headers = auth_headers(client)
    assert client.get("/wholesale/requests/me", headers=headers).json() is None

    created = client.post("/wholesale/requests", json=REQUEST, headers=headers)
    assert created.status_code == 201
    request = created.json()
    assert request["status"] == "PENDING"
    assert request["data"]["categoriesOfInterest"] == ["c-camisetas"]
    assert request["data"]["socialLinks"] is None

    me = client.get("/users/me", headers=headers).json()
    assert me["wholesale"]["requestStatus"] == "PENDING"
    assert "wholesale.request" not in me["permissions"]
    again = client.post("/wholesale/requests", json=REQUEST, headers=headers)
    assert error_of(again)["code"] == "REQUEST_NOT_ALLOWED"

    reviewed = client.post(
        "/_dev/wholesale-review", json={"status": "APPROVED"}, headers=headers
    ).json()
    assert reviewed["request"]["status"] == "APPROVED"
    me = client.get("/users/me", headers=headers).json()
    assert me["role"] == "WHOLESALE"
    assert "wholesale.access" in me["permissions"]


def test_rechazada_puede_volver_a_solicitar(client):
    headers = auth_headers(client)
    client.post("/wholesale/requests", json=REQUEST, headers=headers)
    rejected = client.post(
        "/_dev/wholesale-review", json={"status": "REJECTED"}, headers=headers
    ).json()["request"]
    assert rejected["rejectionReason"] == "No pudimos verificar el NIT del negocio."

    resubmitted = client.post("/wholesale/requests", json=REQUEST, headers=headers).json()
    assert resubmitted["status"] == "PENDING"
    assert resubmitted["id"] == rejected["id"]


def test_solicitud_valida_los_datos_comerciales(client):
    headers = auth_headers(client)
    response = client.post(
        "/wholesale/requests",
        json={**REQUEST, "nit": "90.012", "businessType": "BAR", "categoriesOfInterest": []},
        headers=headers,
    )
    assert response.status_code == 400
    details = error_of(response)["details"]
    assert details["nit"] == "NIT o cédula sin puntos (ej. 900123456-7)."
    assert details["businessType"] == "Elige el tipo de negocio."

    no_categories = client.post(
        "/wholesale/requests", json={**REQUEST, "categoriesOfInterest": ["nada"]}, headers=headers
    )
    assert error_of(no_categories)["details"] == {
        "categoriesOfInterest": "Elige al menos una categoría."
    }


def test_panel_solo_para_mayoristas(client):
    headers = auth_headers(client)
    assert client.get("/wholesale/profile", headers=headers).status_code == 403
    assert client.get("/wholesale/frequent-products", headers=headers).status_code == 403


def test_panel_y_productos_habituales(client):
    headers = wholesale_headers(client)
    address = create_address(client, headers)

    def buy(quantity):
        client.post(
            "/cart/items", json={"variantId": BLACK_M, "quantity": quantity}, headers=headers
        )
        client.post(
            "/orders",
            json={
                "addressId": address["id"],
                "shippingOptionId": "pickup",
                "paymentMethod": "CASH_ON_DELIVERY",
            },
            headers=headers,
        )

    buy(6)
    buy(12)
    profile = client.get("/wholesale/profile", headers=headers).json()
    assert profile["accumulatedPurchase"] == 6 * 31200 + 12 * 27000
    assert profile["totalSavings"] == 6 * 3800 + 12 * 8000
    assert profile["minimumOrder"] == 120000

    frequent = client.get("/wholesale/frequent-products", headers=headers).json()
    assert len(frequent) == 1
    assert frequent[0]["timesOrdered"] == 2
    assert frequent[0]["usualQuantity"] == 9
    assert frequent[0]["pricing"]["unitPrice"] == 31200


def test_promociones_vigentes(client):
    promotions = client.get("/promotions/active").json()
    assert {promotion["type"] for promotion in promotions} <= {"SEASON", "VOLUME", "SHIPPING"}
    assert all("startsAt" in promotion for promotion in promotions)


def test_cuentas_de_prueba(client):
    from app.database import SessionLocal
    from app.seed.demo import DEMO_PASSWORD, WHOLESALE_EMAIL, load_demo

    with SessionLocal() as db:
        assert load_demo(db) is True
        assert load_demo(db) is False

    login = client.post("/auth/login", json={"email": WHOLESALE_EMAIL, "password": DEMO_PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['token']}"}
    assert login.json()["user"]["role"] == "WHOLESALE"

    orders = client.get("/orders", headers=headers).json()
    assert orders["total"] == 3
    assert client.get("/wholesale/profile", headers=headers).json()["accumulatedPurchase"] > 0
    assert len(client.get("/wholesale/frequent-products", headers=headers).json()) == 7
    assert client.get("/lists", headers=headers).json()[0]["itemsCount"] == 4
    assert len(client.get("/favorites", headers=headers).json()) == 3
