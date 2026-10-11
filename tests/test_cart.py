from sqlalchemy import text

from app.database import engine
from tests.conftest import auth_headers, error_of, wholesale_headers

BLACK_M = "camiseta-basica-negro-m"  # 47 en stock
BLACK_L = "camiseta-basica-negro-l"
SOLD_OUT = "camiseta-basica-blanco-s"  # sin stock en el catálogo semilla


def items_by_variant(cart):
    return {item["variant"]["id"]: item for item in cart["items"]}


def test_invitado_cotiza_sin_escalas_y_con_envio(client):
    cart = client.post(
        "/cart/quote",
        json={
            "items": [{"variantId": BLACK_M, "quantity": 1}, {"variantId": BLACK_L, "quantity": 1}]
        },
    ).json()

    assert cart["id"] == "guest"
    # 2 x 35.000 + envío 10.000.
    assert cart["summary"] == {
        "itemsCount": 2,
        "subtotal": 70000,
        "discountTotal": 0,
        "shipping": 10000,
        "total": 80000,
        "savingsTotal": 0,
    }
    assert [incentive["type"] for incentive in cart["incentives"]] == ["FREE_SHIPPING"]
    assert cart["incentives"][0]["remaining"] == 50000
    assert cart["minimumOrder"] is None
    assert cart["items"][0]["id"] == BLACK_M


def test_mayorista_suma_tallas_para_la_escala(client):
    headers = wholesale_headers(client)
    client.post("/cart/items", json={"variantId": BLACK_M, "quantity": 3}, headers=headers)
    cart = client.post(
        "/cart/items", json={"variantId": BLACK_L, "quantity": 2}, headers=headers
    ).json()

    tier = next(i for i in cart["incentives"] if i["type"] == "QUANTITY_TIER")
    assert tier["remaining"] == 1
    assert tier["targetUnitPrice"] == 31200

    line = items_by_variant(cart)[BLACK_L]
    updated = client.patch(
        f"/cart/items/{line['id']}", json={"quantity": 3}, headers=headers
    ).json()
    prices = {item["pricing"]["unitPrice"] for item in updated["items"]}
    assert prices == {31200}
    assert all(item["productQuantity"] == 6 for item in updated["items"])
    assert updated["minimumOrder"] == {"amount": 120000, "remaining": 0, "met": True}


def test_pedido_minimo_mayorista(client):
    headers = wholesale_headers(client)
    cart = client.post(
        "/cart/items", json={"variantId": BLACK_M, "quantity": 2}, headers=headers
    ).json()

    assert cart["minimumOrder"] == {"amount": 120000, "remaining": 50000, "met": False}


def test_cantidad_mayor_al_stock_se_ajusta_y_avisa(client):
    headers = auth_headers(client)
    cart = client.post(
        "/cart/items", json={"variantId": BLACK_M, "quantity": 500}, headers=headers
    ).json()

    assert cart["items"][0]["quantity"] == 47
    assert cart["warnings"][0]["code"] == "STOCK_REDUCED"
    # El ajuste queda guardado.
    assert client.get("/cart", headers=headers).json()["items"][0]["quantity"] == 47


def test_no_agrega_productos_agotados_ni_cantidades_invalidas(client):
    headers = auth_headers(client)

    sold_out = client.post(
        "/cart/items", json={"variantId": SOLD_OUT, "quantity": 1}, headers=headers
    )
    assert sold_out.status_code == 409
    assert error_of(sold_out)["code"] == "OUT_OF_STOCK"

    zero = client.post("/cart/items", json={"variantId": BLACK_M, "quantity": 0}, headers=headers)
    assert zero.status_code == 400

    missing = client.post("/cart/items", json={"variantId": "no", "quantity": 1}, headers=headers)
    assert missing.status_code == 404


def test_cambiar_a_una_variante_que_ya_esta_une_las_lineas(client):
    headers = auth_headers(client)
    client.post("/cart/items", json={"variantId": BLACK_M, "quantity": 2}, headers=headers)
    cart = client.post(
        "/cart/items", json={"variantId": BLACK_L, "quantity": 1}, headers=headers
    ).json()

    line = items_by_variant(cart)[BLACK_L]
    merged = client.patch(
        f"/cart/items/{line['id']}", json={"variantId": BLACK_M}, headers=headers
    ).json()
    assert [(i["variant"]["id"], i["quantity"]) for i in merged["items"]] == [(BLACK_M, 3)]


def test_quitar_y_cantidad_cero(client):
    headers = auth_headers(client)
    client.post("/cart/items", json={"variantId": BLACK_M, "quantity": 2}, headers=headers)
    cart = client.post(
        "/cart/items", json={"variantId": BLACK_L, "quantity": 1}, headers=headers
    ).json()
    lines = items_by_variant(cart)

    after_delete = client.delete(f"/cart/items/{lines[BLACK_L]['id']}", headers=headers).json()
    assert list(items_by_variant(after_delete)) == [BLACK_M]

    after_zero = client.patch(
        f"/cart/items/{lines[BLACK_M]['id']}", json={"quantity": 0}, headers=headers
    ).json()
    assert after_zero["items"] == []


def test_no_toca_lineas_de_otro_usuario(client):
    laura = auth_headers(client, "laura@trama.co")
    carlos = auth_headers(client, "carlos@trama.co")
    line = client.post(
        "/cart/items", json={"variantId": BLACK_M, "quantity": 2}, headers=laura
    ).json()["items"][0]

    response = client.patch(f"/cart/items/{line['id']}", json={"quantity": 9}, headers=carlos)
    assert response.status_code == 404
    client.delete(f"/cart/items/{line['id']}", headers=carlos)
    assert client.get("/cart", headers=laura).json()["items"][0]["quantity"] == 2


def test_fusiona_el_carrito_de_invitado(client):
    headers = auth_headers(client)
    client.post("/cart/items", json={"variantId": BLACK_M, "quantity": 1}, headers=headers)
    cart = client.post(
        "/cart/merge",
        json={
            "items": [
                {"variantId": BLACK_M, "quantity": 2},
                {"variantId": BLACK_L, "quantity": 1},
                {"variantId": "no-existe", "quantity": 1},
            ]
        },
        headers=headers,
    ).json()

    assert {i["variant"]["id"]: i["quantity"] for i in cart["items"]} == {BLACK_M: 3, BLACK_L: 1}


def test_agregar_varios_omite_los_agotados(client):
    headers = auth_headers(client)
    cart = client.post(
        "/cart/items/bulk",
        json={
            "items": [
                {"variantId": BLACK_M, "quantity": 12},
                {"variantId": SOLD_OUT, "quantity": 12},
            ]
        },
        headers=headers,
    ).json()

    assert list(items_by_variant(cart)) == [BLACK_M]


def test_variante_que_se_agota_queda_fuera_del_total(client):
    headers = auth_headers(client)
    client.post("/cart/items", json={"variantId": BLACK_M, "quantity": 2}, headers=headers)
    with engine.begin() as connection:
        connection.execute(text(f"UPDATE product_variants SET stock = 0 WHERE id = '{BLACK_M}'"))

    cart = client.get("/cart", headers=headers).json()
    assert cart["items"][0]["available"] is False
    assert cart["warnings"][0]["code"] == "OUT_OF_STOCK"
    assert cart["summary"]["total"] == 0


def test_carrito_requiere_sesion(client):
    assert client.get("/cart").status_code == 401
