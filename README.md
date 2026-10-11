# Trama — API

Backend de Trama, tienda de ropa con compra individual y compra por volumen para mayoristas: catálogo con precios calculados en el servidor, carrito, checkout con Mercado Pago, pedidos, cuentas, listas de compra, programa mayorista e inspiraciones guardadas (fotos de Pexels).

FastAPI · PostgreSQL · SQLAlchemy 2 · Alembic · Pydantic · Argon2 · PyJWT · httpx · pytest · ruff

API desplegada: https://api-devama.duckdns.org · Tienda: https://devama.duckdns.org

## Requisitos

- Python 3.12+
- PostgreSQL 15+

## Puesta en marcha (desarrollo)

1. Crea el usuario y las bases (en `psql` como `postgres`):

   ```sql
   CREATE ROLE trama WITH LOGIN PASSWORD 'trama_dev';
   CREATE DATABASE trama OWNER trama;
   CREATE DATABASE trama_test OWNER trama;
   ```

2. Entorno virtual y dependencias:

   ```bash
   python -m venv .venv
   .venv/Scripts/activate        # Windows (en Linux/macOS: source .venv/bin/activate)
   pip install -r requirements-dev.txt
   ```

3. Tablas, datos y arranque:

   ```bash
   alembic upgrade head
   python -m app seed --demo
   python -m app dev
   ```

La API queda en `http://localhost:3000` y la documentación interactiva en `http://localhost:3000/docs`.

En desarrollo no hace falta `.env`: los valores por defecto están en `app/config.py`.

### Cuentas de prueba

`python -m app seed --demo` crea dos cuentas (contraseña `Trama1234`, pública: no usar para nada real):

| Perfil    | Correo                    | Qué trae                                                   |
| --------- | ------------------------- | ---------------------------------------------------------- |
| Comprador | `comprador@demo.trama.co` | Cuenta vacía                                               |
| Mayorista | `mayorista@demo.trama.co` | Dirección, 3 pedidos, lista "Pedido mensual" y 3 favoritos |

## Comandos

| Comando                                | Qué hace                                                    |
| -------------------------------------- | ----------------------------------------------------------- |
| `python -m app dev`                    | Desarrollo con recarga automática                           |
| `python -m app start`                  | Producción, sin recarga                                     |
| `python -m app seed [--demo]`          | Carga o actualiza el catálogo; `--demo`: cuentas de prueba  |
| `alembic upgrade head`                 | Aplica las migraciones                                      |
| `alembic revision --autogenerate -m …` | Crea una migración a partir de los modelos                  |
| `pytest`                               | Tests (usan la base `trama_test`)                           |
| `ruff check .` / `ruff format .`       | Lint y formato                                              |

## Endpoints

✔ = exige `Authorization: Bearer <token>`. · = pública, pero con un token válido el precio se calcula para ese usuario.

### Cuenta

| Método | Ruta                          | Auth | Descripción                                                          |
| ------ | ----------------------------- | :--: | -------------------------------------------------------------------- |
| POST   | `/signup`                     |      | `{ email, password, name }` → 201 `{ id, email, name }`              |
| POST   | `/signin`                     |      | `{ email, password }` → `{ token }` (JWT, 7 días)                    |
| POST   | `/auth/register`              |      | Como `/signup` + `acceptTerms` → 201 `{ token, user }`               |
| POST   | `/auth/login`                 |      | → `{ token, user }`                                                  |
| POST   | `/auth/logout`                |      | 204 (el cliente borra el token)                                      |
| POST   | `/auth/password/forgot`       |      | `{ email }` → mensaje (igual exista o no la cuenta)                  |
| POST   | `/auth/password/reset`        |      | `{ token, password }`: enlace de un solo uso, 30 minutos             |
| GET    | `/users/me`                   |  ✔   | `{ id, email, name, phone, role, wholesale, permissions }`           |
| PATCH  | `/users/me`                   |  ✔   | `{ name?, phone? }`                                                  |
| POST   | `/users/me/password`          |  ✔   | `{ currentPassword, newPassword }`                                   |
| CRUD   | `/users/me/addresses[/{id}]`  |  ✔   | Direcciones; la primera queda predeterminada                         |

### Catálogo

| Método | Ruta               | Auth | Descripción                                                                                                       |
| ------ | ------------------ | :--: | ----------------------------------------------------------------------------------------------------------------- |
| GET    | `/categories`      |      | Categorías con conteo de productos e imagen                                                                       |
| GET    | `/products`        |  ·   | `q` (sin tildes), `category`, `size`, `color`, `minPrice`, `maxPrice`, `tag`, `onSale`, `sort`, `page`, `pageSize` |
| GET    | `/products/lookup` |  ·   | Variantes por nombre o SKU (pedido rápido)                                                                        |
| GET    | `/products/{slug}` |  ·   | Detalle con variantes y stock                                                                                     |
| POST   | `/pricing/quote`   |  ·   | `{ items: [{ variantId, quantity }] }` → precio con su escala                                                     |
| GET    | `/promotions/active` |    | Promociones vigentes hoy                                                                                          |

### Compra

| Método | Ruta                                    | Auth | Descripción                                                          |
| ------ | --------------------------------------- | :--: | -------------------------------------------------------------------- |
| GET    | `/cart`                                 |  ✔   | Carrito con precios, avisos de stock, incentivos y pedido mínimo     |
| POST   | `/cart/items` · `/cart/items/bulk`      |  ✔   | Agregar una variante o varias                                        |
| PATCH  | `/cart/items/{id}`                      |  ✔   | Cambiar cantidad o variante (une líneas repetidas)                   |
| DELETE | `/cart/items/{id}`                      |  ✔   | Quitar                                                               |
| POST   | `/cart/merge`                           |  ✔   | Suma el carrito de invitado al iniciar sesión                        |
| POST   | `/cart/quote`                           |  ·   | Carrito de invitado (no se guarda)                                   |
| GET    | `/checkout/shipping-options?addressId=` |  ✔   | Opciones de envío con el total de cada una                           |
| POST   | `/orders`                               |  ✔   | `{ addressId, shippingOptionId, paymentMethod, notes }` → `{ order, payment: { redirectUrl } }` |
| GET    | `/orders?group=&page=&pageSize=`        |  ✔   | Historial (`active`, `delivered`, `cancelled`)                       |
| GET    | `/orders/{id}`                          |  ✔   | Detalle                                                              |
| POST   | `/orders/{id}/cancel`                   |  ✔   | `{ reason }`; devuelve el stock                                      |
| POST   | `/orders/{id}/reorder`                  |  ✔   | Agrega al carrito lo que siga disponible                             |
| POST   | `/orders/{id}/payment`                  |  ✔   | Nuevo intento de pago con Mercado Pago                               |
| POST   | `/payments/mercadopago/webhook`         |      | Avisos de Mercado Pago (firma verificada)                            |

### Favoritos, listas e inspiraciones

| Método           | Ruta                            | Auth | Descripción                                        |
| ---------------- | ------------------------------- | :--: | -------------------------------------------------- |
| GET              | `/favorites`                    |  ✔   | Productos favoritos, del más reciente              |
| PUT / DELETE     | `/favorites/{productId}`        |  ✔   | 204                                                |
| GET / POST       | `/lists`                        |  ✔   | Listas de compra (nombre único por usuario)        |
| GET/PATCH/DELETE | `/lists/{id}`                   |  ✔   | Detalle con precios, renombrar, borrar             |
| POST             | `/lists/{id}/items`             |  ✔   | `{ variantId, quantity }` (suma si ya está)        |
| PATCH / DELETE   | `/lists/{id}/items/{itemId}`    |  ✔   | Cantidad o quitar                                  |
| POST             | `/lists/{id}/add-to-cart`       |  ✔   | Todo lo disponible al carrito                      |
| GET / POST       | `/inspirations`                 |  ✔   | Fotos de Pexels guardadas                          |
| DELETE           | `/inspirations/{id}`            |  ✔   | Solo las propias (403 si es de otro)               |

### Mayoristas

| Método | Ruta                            | Auth | Descripción                                                   |
| ------ | ------------------------------- | :--: | ------------------------------------------------------------- |
| GET    | `/wholesale/program`            |      | Pedido mínimo y beneficios                                    |
| GET    | `/wholesale/requests/me`        |  ✔   | Solicitud actual o `null`                                     |
| POST   | `/wholesale/requests`           |  ✔   | Datos comerciales (NIT, tipo de negocio, volumen…)            |
| GET    | `/wholesale/profile`            |  ✔   | Compra acumulada y ahorro del año (solo mayoristas)           |
| GET    | `/wholesale/frequent-products`  |  ✔   | Variantes más compradas con su cantidad habitual              |
| POST   | `/_dev/wholesale-review`        |  ✔   | **Solo fuera de producción**: simula la revisión del admin    |

## Reglas de negocio

- **Precios**: el backend calcula todo (el frontend solo muestra): precio base → precio de temporada → escala por cantidad. Las escalas (media docena, docena…) son **exclusivas de las cuentas mayoristas** y suman todas las tallas y colores del mismo producto. Dinero en enteros COP, IVA incluido, redondeado a la centena.
- **Envío**: estándar $10.000, gratis desde $120.000 en productos; express $24.000 en ciudades principales; recogida en bodega gratis.
- **Pedido mínimo mayorista**: $120.000 en productos.
- **Stock**: se descuenta al crear el pedido (con bloqueo de filas para que dos compras no se lleven las mismas unidades) y vuelve al cancelar.
- **Mercado Pago (Checkout Pro)**: el pedido nace en `PENDING_PAYMENT`, el cliente paga en Mercado Pago y el webhook confirma el pago consultando la API y comparando el monto. Sin `MP_ACCESS_TOKEN` el pago se simula y se aprueba al instante.

## Errores

Todas las respuestas de error tienen el mismo formato (los campos en camelCase, como los envía el frontend):

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Revisa los datos enviados.", "details": { "email": "Ingresa un correo válido." } } }
```

| Código | Cuándo                                                                         |
| ------ | ------------------------------------------------------------------------------ |
| 400    | Cuerpo o parámetros no válidos (se valida antes de llegar al controlador)      |
| 401    | Sin token, token no válido o expirado, o credenciales incorrectas              |
| 403    | Recurso de otro usuario o sección solo para mayoristas                         |
| 404    | El recurso no existe                                                           |
| 409    | Correo ya registrado, foto ya guardada, sin stock o solicitud ya enviada       |
| 422    | Regla de negocio (carrito vacío, pedido mínimo, pedido que no se puede cancelar) |
| 500    | Error no previsto (el detalle solo va a `error.log`)                           |

## Seguridad

- Contraseñas con Argon2. El hash no se lee de la base salvo al verificarlo y nunca se devuelve.
- Correos sin distinguir mayúsculas. Un correo inexistente y una contraseña incorrecta responden igual y tardan lo mismo.
- Enlaces de recuperación de un solo uso; en la base solo se guarda su hash.
- Cada usuario solo ve y modifica lo suyo (direcciones, carrito, pedidos, listas, inspiraciones).
- El webhook de Mercado Pago verifica la firma `x-signature` y nunca confía en el contenido del aviso.
- `/docs`, el esquema OpenAPI y `/_dev/*` solo existen fuera de producción.

## Registros

En `LOG_DIR` (por defecto `logs/`, fuera del repositorio), una línea JSON por evento:

- `request.log`: todas las solicitudes (método, ruta, estado, duración, IP).
- `error.log`: los errores devueltos por la API; los 500 incluyen el traceback.

Nunca se registran cuerpos ni encabezados (contraseñas, tokens).

## Variables de entorno

Ver `.env.example`. El `.env` solo existe en el servidor.

| Variable            | Por defecto (desarrollo)                                              |
| ------------------- | --------------------------------------------------------------------- |
| `ENV`               | `development` (`production` en el servidor)                           |
| `DATABASE_URL`      | `postgresql+psycopg://trama:trama_dev@localhost:5432/trama`           |
| `JWT_SECRET`        | clave de desarrollo; **obligatoria** con `ENV=production`             |
| `JWT_EXPIRES_DAYS`  | `7`                                                                   |
| `CORS_ORIGINS`      | `["http://localhost:5173"]`                                           |
| `FRONTEND_URL`      | `http://localhost:5173` (retorno desde Mercado Pago)                  |
| `API_URL`           | `http://localhost:3000` (webhook de Mercado Pago; debe ser https)     |
| `MP_ACCESS_TOKEN`   | vacío: pago simulado                                                  |
| `MP_WEBHOOK_SECRET` | vacío; **obligatoria** si hay `MP_ACCESS_TOKEN`                       |
| `LOG_DIR`           | `logs`                                                                |
| `HOST` / `PORT`     | `127.0.0.1` / `3000`                                                  |

## Despliegue (resumen)

1. En el servidor: Python 3.12, PostgreSQL y nginx. Crea el usuario y la base con una contraseña fuerte.
2. Clona el repositorio, crea el entorno virtual e instala `requirements.txt`.
3. Crea `.env` a partir de `.env.example` (`ENV=production`, `JWT_SECRET` nuevo, `DATABASE_URL`, `CORS_ORIGINS`, `FRONTEND_URL` y `API_URL` con los dominios reales).
4. `alembic upgrade head` y `python -m app seed` (con `--demo` si quieres las cuentas de prueba).
5. Servicio `systemd` (o `pm2`) que ejecute `.venv/bin/python -m app start` en el directorio del proyecto.
6. nginx como proxy de `api.<dominio>` hacia `127.0.0.1:3000` y certificado HTTPS con `certbot --nginx`.
