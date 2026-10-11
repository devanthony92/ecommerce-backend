from tests.conftest import auth_headers, error_of, wholesale_headers


def test_categorias_con_conteo_e_imagen(client):
    categories = client.get("/categories").json()

    assert [category["slug"] for category in categories][:3] == ["camisetas", "camisas", "jeans"]
    assert len(categories) == 7
    assert sum(category["productCount"] for category in categories) == 32
    assert all(category["image"]["url"].startswith("data:image/svg+xml") for category in categories)


def test_lista_paginada_con_facetas(client):
    body = client.get("/products").json()

    assert body["total"] == 32
    assert body["pageSize"] == 12
    assert body["totalPages"] == 3
    assert len(body["items"]) == 12
    assert {"sizes", "colors", "priceRange"} <= body["facets"].keys()

    last = client.get("/products", params={"page": 3}).json()
    assert len(last["items"]) == 8


def test_filtra_por_categoria(client):
    body = client.get("/products", params={"category": "gorras"}).json()

    assert body["total"] == 4
    assert {item["category"]["slug"] for item in body["items"]} == {"gorras"}


def test_busqueda_ignora_tildes_y_mayusculas(client):
    body = client.get("/products", params={"q": "RINONERA"}).json()

    assert [item["name"] for item in body["items"]] == ["Riñonera urbana"]


def test_busqueda_incluye_el_nombre_de_la_categoria(client):
    body = client.get("/products", params={"q": "jeans"}).json()
    assert body["total"] == 5


def test_filtros_de_talla_y_color_mantienen_las_facetas_de_la_base(client):
    everything = client.get("/products", params={"category": "camisetas"}).json()
    body = client.get(
        "/products", params={"category": "camisetas", "color": "Blanco", "size": ["XS", "XL"]}
    ).json()

    assert 0 < body["total"] < everything["total"]
    assert body["facets"] == everything["facets"]
    # Con filtro de color, la imagen de la tarjeta es la de ese color.
    assert {item["image"]["color"] for item in body["items"]} == {"Blanco"}


def test_solo_ofertas(client):
    body = client.get("/products", params={"onSale": "true", "pageSize": 48}).json()

    assert body["total"] > 0
    assert all(item["pricing"]["compareAtPrice"] for item in body["items"])


def test_orden_por_precio(client):
    items = client.get("/products", params={"sort": "price_asc", "pageSize": 48}).json()["items"]
    prices = [item["pricing"]["unitPrice"] for item in items]

    assert prices == sorted(prices)


def test_detalle_publico_sin_escalas(client):
    product = client.get("/products/camiseta-basica").json()

    assert product["name"] == "Camiseta básica"
    assert product["pricing"]["audience"] == "PUBLIC"
    assert product["pricing"]["unitPrice"] == 35000
    assert product["pricing"]["tiers"] == []
    assert product["pricing"]["nextTier"] is None
    assert [option["name"] for option in product["options"]] == ["color", "size"]
    assert product["variants"][0]["id"] == "camiseta-basica-negro-xs"


def test_detalle_mayorista_con_escalas(client):
    headers = wholesale_headers(client)
    pricing = client.get("/products/camiseta-basica", headers=headers).json()["pricing"]

    assert pricing["audience"] == "WHOLESALE"
    assert [tier["minQty"] for tier in pricing["tiers"]] == [1, 6, 12, 24]
    # 35.000 menos 11 % = 31.150 → 31.200 (redondeo a la centena).
    assert pricing["tiers"][1]["unitPrice"] == 31200
    assert pricing["nextTier"] == {
        "minQty": 6,
        "label": "Media docena",
        "unitPrice": 31200,
        "unitsToReach": 5,
    }


def test_token_no_valido_en_ruta_publica_responde_como_visitante(client):
    response = client.get("/products/camiseta-basica", headers={"Authorization": "Bearer x"})

    assert response.status_code == 200
    assert response.json()["pricing"]["audience"] == "PUBLIC"


def test_producto_inexistente(client):
    response = client.get("/products/no-existe")

    assert response.status_code == 404
    assert error_of(response)["code"] == "PRODUCT_NOT_FOUND"


def test_lookup_por_nombre_y_por_sku(client):
    by_name = client.get("/products/lookup", params={"q": "gorra trucker"}).json()
    assert {item["productSlug"] for item in by_name} == {"gorra-trucker"}

    sku = by_name[0]["sku"]
    by_sku = client.get("/products/lookup", params={"q": sku.lower()}).json()
    assert [item["sku"] for item in by_sku] == [sku]

    assert client.get("/products/lookup", params={"q": "g"}).json() == []
    assert len(client.get("/products/lookup", params={"q": "camiseta"}).json()) == 12


def test_cotizacion_mayorista_aplica_la_escala(client):
    headers = wholesale_headers(client)
    response = client.post(
        "/pricing/quote",
        json={"items": [{"variantId": "camiseta-basica-negro-m", "quantity": 6}]},
        headers=headers,
    )

    pricing = response.json()["items"][0]["pricing"]
    assert pricing["unitPrice"] == 31200
    assert pricing["lineTotal"] == 187200
    assert {"type": "QUANTITY_TIER", "label": "Media docena", "minQty": 6} in pricing[
        "appliedRules"
    ]


def test_cotizacion_comprador_paga_precio_unidad(client):
    headers = auth_headers(client)
    response = client.post(
        "/pricing/quote",
        json={"items": [{"variantId": "camiseta-basica-negro-m", "quantity": 6}]},
        headers=headers,
    )

    pricing = response.json()["items"][0]["pricing"]
    assert pricing["audience"] == "BUYER"
    assert pricing["unitPrice"] == 35000


def test_cotizacion_variante_inexistente(client):
    response = client.post("/pricing/quote", json={"items": [{"variantId": "no", "quantity": 1}]})

    assert response.status_code == 404
    assert error_of(response)["details"] == {"variantId": "no"}
