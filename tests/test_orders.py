import hashlib
import hmac

import pytest
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from app.services import mercadopago
from app.services.orders import reserve_stock
from tests.conftest import auth_headers, create_address, error_of, wholesale_headers

BLACK_M = "camiseta-basica-negro-m"  # 47 en stock
JEAN = "jean-slim-denim-30"


def stock_of(variant_id: str) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT stock FROM product_variants WHERE id = :id"), {"id": variant_id}
        ).scalar_one()


def fill_cart(client, headers, variant_id=BLACK_M, quantity=4):
    client.post(
        "/cart/items", json={"variantId": variant_id, "quantity": quantity}, headers=headers
    )


def place_order(client, headers, address_id, shipping="standard", payment="CASH_ON_DELIVERY"):
    return client.post(
        "/orders",
        json={
            "addressId": address_id,
            "shippingOptionId": shipping,
            "paymentMethod": payment,
            "notes": "  Timbre dañado  ",
        },
        headers=headers,
    )


# --- Envío -----------------------------------------------------------------------


def test_opciones_de_envio_en_ciudad_principal(client):
    headers = auth_headers(client)
    address = create_address(client, headers)
    fill_cart(client, headers, quantity=2)

    options = client.get(
        "/checkout/shipping-options", params={"addressId": address["id"]}, headers=headers
    ).json()

    assert [(o["id"], o["price"], o["total"]) for o in options] == [
        ("standard", 10000, 80000),
        ("express", 24000, 94000),
        ("pickup", 0, 70000),
    ]


def test_envio_estandar_gratis_desde_120000_y_sin_express_fuera_de_ciudades(client):
    headers = auth_headers(client)
    address = create_address(client, headers, city="Rionegro")
    fill_cart(client, headers, quantity=4)

    options = client.get(
        "/checkout/shipping-options", params={"addressId": address["id"]}, headers=headers
    ).json()

    assert [o["id"] for o in options] == ["standard", "pickup"]
    assert options[0]["price"] == 0
    assert options[0]["description"] == "Gratis por compras desde $120.000"


# --- Crear pedido ----------------------------------------------------------------


def test_pedido_contra_entrega_descuenta_stock_y_vacia_el_carrito(client):
    headers = auth_headers(client)
    address = create_address(client, headers)
    fill_cart(client, headers, quantity=4)

    response = place_order(client, headers, address["id"])

    assert response.status_code == 201
    body = response.json()
    order = body["order"]
    assert body["payment"] == {"redirectUrl": None}
    assert order["number"] == "PED-000001"
    assert order["status"] == "PROCESSING"
    assert order["summary"] == {
        "itemsCount": 4,
        "subtotal": 140000,
        "discountTotal": 0,
        "shipping": 0,
        "total": 140000,
    }
    assert order["address"]["city"] == "Medellín"
    assert order["payment"] == {"method": "CASH_ON_DELIVERY", "label": "Pago contra entrega"}
    assert order["notes"] == "Timbre dañado"
    assert order["canCancel"] is True
    assert order["createdAt"].endswith("Z")

    assert stock_of(BLACK_M) == 43
    assert client.get("/cart", headers=headers).json()["items"] == []
    assert client.get(f"/orders/{order['id']}", headers=headers).json()["id"] == order["id"]


def test_pedido_con_mercado_pago_simulado_queda_pagado(client):
    headers = auth_headers(client)
    address = create_address(client, headers)
    fill_cart(client, headers)

    body = place_order(client, headers, address["id"], payment="MERCADO_PAGO").json()

    assert body["order"]["status"] == "PAID"
    assert body["payment"]["redirectUrl"] == (
        f"/checkout/confirmacion/{body['order']['id']}?status=approved"
    )


def test_mayorista_bajo_el_minimo_no_puede_comprar(client):
    headers = wholesale_headers(client)
    address = create_address(client, headers)
    fill_cart(client, headers, quantity=2)

    response = place_order(client, headers, address["id"])

    assert response.status_code == 422
    assert error_of(response)["code"] == "MINIMUM_ORDER_NOT_MET"
    assert error_of(response)["message"] == (
        "El pedido mínimo mayorista es de $120.000 en productos."
    )


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"addressId": 999}, "ADDRESS_REQUIRED"),
        ({"shippingOptionId": "dron"}, "SHIPPING_REQUIRED"),
        ({"paymentMethod": "PSE"}, "PAYMENT_REQUIRED"),
    ],
)
def test_datos_de_checkout_no_validos(client, changes, code):
    headers = auth_headers(client)
    address = create_address(client, headers)
    fill_cart(client, headers)
    body = {
        "addressId": address["id"],
        "shippingOptionId": "standard",
        "paymentMethod": "CASH_ON_DELIVERY",
        **changes,
    }

    response = client.post("/orders", json=body, headers=headers)
    assert response.status_code == 422
    assert error_of(response)["code"] == code


def test_carrito_vacio(client):
    headers = auth_headers(client)
    address = create_address(client, headers)

    response = place_order(client, headers, address["id"])
    assert error_of(response)["code"] == "CART_EMPTY"


def test_no_puede_usar_la_direccion_de_otro(client):
    laura = auth_headers(client, "laura@trama.co")
    carlos = auth_headers(client, "carlos@trama.co")
    address = create_address(client, laura)
    fill_cart(client, carlos)

    assert error_of(place_order(client, carlos, address["id"]))["code"] == "ADDRESS_REQUIRED"


def test_no_vende_mas_unidades_de_las_que_hay(client):
    from app.database import SessionLocal
    from app.errors import AppError

    with SessionLocal() as db, pytest.raises(AppError) as error:
        reserve_stock(db, {BLACK_M: 48})
    assert error.value.code == "OUT_OF_STOCK"
    assert stock_of(BLACK_M) == 47


# --- Historial, cancelación y recompra -------------------------------------------


def test_historial_filtra_y_pagina(client):
    headers = auth_headers(client)
    address = create_address(client, headers)
    for _ in range(3):
        fill_cart(client, headers, quantity=1)
        place_order(client, headers, address["id"])
    first = client.get("/orders", headers=headers).json()["items"][-1]
    client.post(f"/orders/{first['id']}/cancel", json={}, headers=headers)

    page = client.get("/orders", params={"pageSize": 2}, headers=headers).json()
    assert (page["total"], page["totalPages"], len(page["items"])) == (3, 2, 2)
    assert page["items"][0]["number"] == "PED-000003"

    cancelled = client.get("/orders", params={"group": "cancelled"}, headers=headers).json()
    assert [order["id"] for order in cancelled["items"]] == [first["id"]]
    active = client.get("/orders", params={"group": "active"}, headers=headers).json()
    assert active["total"] == 2


def test_cancelar_devuelve_el_stock(client):
    headers = auth_headers(client)
    address = create_address(client, headers)
    fill_cart(client, headers, quantity=5)
    order = place_order(client, headers, address["id"]).json()["order"]
    assert stock_of(BLACK_M) == 42

    cancelled = client.post(
        f"/orders/{order['id']}/cancel", json={"reason": "Me equivoqué"}, headers=headers
    ).json()

    assert cancelled["status"] == "CANCELLED"
    assert cancelled["cancelReason"] == "Me equivoqué"
    assert cancelled["canCancel"] is False
    assert stock_of(BLACK_M) == 47

    again = client.post(f"/orders/{order['id']}/cancel", json={}, headers=headers)
    assert error_of(again)["code"] == "ORDER_NOT_CANCELLABLE"


def test_recompra_agrega_lo_disponible_y_avisa_lo_agotado(client):
    headers = auth_headers(client)
    address = create_address(client, headers)
    fill_cart(client, headers, BLACK_M, 2)
    fill_cart(client, headers, JEAN, 1)
    order = place_order(client, headers, address["id"]).json()["order"]
    with engine.begin() as connection:
        connection.execute(text(f"UPDATE product_variants SET stock = 0 WHERE id = '{JEAN}'"))

    cart = client.post(f"/orders/{order['id']}/reorder", headers=headers).json()

    assert [(i["variant"]["id"], i["quantity"]) for i in cart["items"]] == [(BLACK_M, 2)]
    assert cart["warnings"][0]["code"] == "REORDER_UNAVAILABLE"


def test_pedido_de_otro_usuario_no_existe(client):
    laura = auth_headers(client, "laura@trama.co")
    carlos = auth_headers(client, "carlos@trama.co")
    address = create_address(client, laura)
    fill_cart(client, laura)
    order = place_order(client, laura, address["id"]).json()["order"]

    for method, path in (
        ("GET", f"/orders/{order['id']}"),
        ("POST", f"/orders/{order['id']}/cancel"),
        ("POST", f"/orders/{order['id']}/reorder"),
    ):
        assert client.request(method, path, json={}, headers=carlos).status_code == 404


# --- Mercado Pago (pasarela real, con la API simulada en el test) ----------------

SECRET = "clave-del-webhook"


@pytest.fixture
def mercado_pago(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "mp_access_token", "TEST-token")
    monkeypatch.setattr(settings, "mp_webhook_secret", SECRET)
    payments: dict[str, dict] = {}
    monkeypatch.setattr(
        mercadopago, "create_preference", lambda order: f"https://mp.test/init/{order.id}"
    )
    monkeypatch.setattr(mercadopago, "get_payment", lambda payment_id: payments[payment_id])
    return payments


def signed_headers(payment_id: str, request_id: str = "req-1", ts: str = "1700000000"):
    manifest = f"id:{payment_id};request-id:{request_id};ts:{ts};"
    signature = hmac.new(SECRET.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return {"x-signature": f"ts={ts},v1={signature}", "x-request-id": request_id}


def notify(client, payment_id, headers=None):
    return client.post(
        "/payments/mercadopago/webhook",
        params={"data.id": payment_id, "type": "payment"},
        json={"type": "payment", "data": {"id": payment_id}},
        headers=headers if headers is not None else signed_headers(payment_id),
    )


def test_mercado_pago_redirige_y_el_webhook_confirma_el_pago(client, mercado_pago):
    headers = auth_headers(client)
    address = create_address(client, headers)
    fill_cart(client, headers)
    body = place_order(client, headers, address["id"], payment="MERCADO_PAGO").json()
    order = body["order"]

    assert order["status"] == "PENDING_PAYMENT"
    assert body["payment"]["redirectUrl"] == f"https://mp.test/init/{order['id']}"

    mercado_pago["555"] = {
        "status": "approved",
        "external_reference": str(order["id"]),
        "transaction_amount": order["summary"]["total"],
    }
    assert notify(client, "555").status_code == 200
    assert client.get(f"/orders/{order['id']}", headers=headers).json()["status"] == "PAID"


def test_webhook_con_firma_no_valida_se_rechaza(client, mercado_pago):
    response = notify(client, "555", headers={"x-signature": "ts=1,v1=falsa", "x-request-id": "r"})
    assert response.status_code == 401


def test_webhook_con_monto_distinto_no_aprueba(client, mercado_pago):
    headers = auth_headers(client)
    address = create_address(client, headers)
    fill_cart(client, headers)
    order = place_order(client, headers, address["id"], payment="MERCADO_PAGO").json()["order"]
    mercado_pago["556"] = {
        "status": "approved",
        "external_reference": str(order["id"]),
        "transaction_amount": 1000,
    }

    notify(client, "556")
    assert (
        client.get(f"/orders/{order['id']}", headers=headers).json()["status"] == "PENDING_PAYMENT"
    )


def test_pago_rechazado_se_puede_reintentar(client, mercado_pago):
    headers = auth_headers(client)
    address = create_address(client, headers)
    fill_cart(client, headers)
    order = place_order(client, headers, address["id"], payment="MERCADO_PAGO").json()["order"]
    mercado_pago["557"] = {"status": "rejected", "external_reference": str(order["id"])}
    notify(client, "557")

    retry = client.post(f"/orders/{order['id']}/payment", headers=headers)
    assert retry.json() == {"redirectUrl": f"https://mp.test/init/{order['id']}"}


def test_no_se_reintenta_el_pago_de_un_pedido_pagado(client):
    headers = auth_headers(client)
    address = create_address(client, headers)
    fill_cart(client, headers)
    order = place_order(client, headers, address["id"], payment="MERCADO_PAGO").json()["order"]

    response = client.post(f"/orders/{order['id']}/payment", headers=headers)
    assert error_of(response)["code"] == "ORDER_NOT_PAYABLE"
