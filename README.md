# Trama — API

Backend de la tienda Trama: catálogo con precios calculados en el servidor, registro e inicio de sesión con JWT e inspiraciones guardadas (fotos de Pexels que el usuario guarda desde el frontend).

FastAPI · PostgreSQL · SQLAlchemy 2 · Alembic · Pydantic · Argon2 · PyJWT · pytest · ruff

API desplegada: _pendiente_

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

3. Tablas y arranque:

   ```bash
   alembic upgrade head
   python -m app seed
   python -m app dev
   ```

La API queda en `http://localhost:3000` y la documentación interactiva en `http://localhost:3000/docs`.

En desarrollo no hace falta `.env`: los valores por defecto están en `app/config.py`.

## Comandos

| Comando                                | Qué hace                                         |
| -------------------------------------- | ------------------------------------------------ |
| `python -m app dev`                    | Desarrollo con recarga automática                |
| `python -m app start`                  | Producción, sin recarga                          |
| `python -m app seed`                   | Carga o actualiza el catálogo (idempotente)      |
| `alembic upgrade head`                 | Aplica las migraciones                           |
| `alembic revision --autogenerate -m …` | Crea una migración a partir de los modelos       |
| `pytest`                               | Tests (usan la base `trama_test`)                |
| `ruff check .` / `ruff format .`       | Lint y formato                                   |

## Endpoints

| Método | Ruta                 | Auth | Descripción                                                    |
| ------ | -------------------- | :--: | -------------------------------------------------------------- |
| POST   | `/signup`            |      | Crea un usuario `{ email, password, name }` → 201 `User`       |
| POST   | `/signin`            |      | `{ email, password }` → `{ token }` (JWT, 7 días)              |
| GET    | `/users/me`          |  ✔   | Usuario conectado `{ id, email, name }`                        |
| GET    | `/inspirations`      |  ✔   | Inspiraciones del usuario, de la más reciente a la más antigua |
| POST   | `/inspirations`      |  ✔   | Guarda una foto → 201                                          |
| DELETE | `/inspirations/{id}` |  ✔   | Borra una inspiración propia → 200 con la borrada              |
| GET    | `/categories`        |      | Categorías con conteo de productos e imagen                    |
| GET    | `/products`          |  ·   | Catálogo: `q`, `category`, `size`, `color`, `minPrice`, `maxPrice`, `tag`, `onSale`, `sort`, `page`, `pageSize` |
| GET    | `/products/lookup`   |  ·   | Variantes por nombre o SKU (pedido rápido)                     |
| GET    | `/products/{slug}`   |  ·   | Detalle con variantes y stock                                  |
| POST   | `/pricing/quote`     |  ·   | `{ items: [{ variantId, quantity }] }` → precio con su escala  |
| GET    | `/health`            |      | Estado de la API                                               |

Las rutas protegidas (✔) exigen `Authorization: Bearer <token>`. Las marcadas con `·` son públicas, pero si llega un token válido el precio se calcula para ese usuario.

### Precios

El backend calcula todos los precios (el frontend solo los muestra): precio base → precio de temporada → escala por cantidad. Las escalas (media docena, docena…) son **exclusivas de las cuentas mayoristas**; visitantes y compradores pagan el precio por unidad. Dinero en enteros COP, IVA incluido, redondeado a la centena.

```json
// POST /inspirations
{
  "keyword": "denim",
  "pexelsId": 1043474,
  "alt": "Persona con chaqueta de jean",
  "photographer": "Daniel Xavier",
  "photographerUrl": "https://www.pexels.com/@danxavier",
  "link": "https://www.pexels.com/photo/1043474/",
  "image": "https://images.pexels.com/photos/1043474/portrait.jpeg"
}
```

### Errores

Todas las respuestas de error tienen el mismo formato:

```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Revisa los datos enviados.", "details": { "email": "Ingresa un correo válido." } } }
```

| Código | Cuándo                                                                    |
| ------ | ------------------------------------------------------------------------- |
| 400    | Cuerpo o parámetros no válidos (se valida antes de llegar al controlador) |
| 401    | Sin token, token no válido o expirado, o credenciales incorrectas         |
| 403    | Borrar una inspiración de otro usuario                                    |
| 404    | El recurso no existe                                                      |
| 409    | Correo ya registrado o foto ya guardada                                   |
| 500    | Error no previsto (el detalle solo va a `error.log`)                      |

## Seguridad

- Contraseñas con Argon2. El hash no se lee de la base salvo al iniciar sesión y nunca se devuelve.
- Correos sin distinguir mayúsculas. Un correo inexistente y una contraseña incorrecta responden igual y tardan lo mismo.
- Cada usuario solo ve y borra sus propias inspiraciones; el dueño no se expone en las respuestas.
- `/docs` y el esquema OpenAPI solo existen fuera de producción.

## Registros

En `LOG_DIR` (por defecto `logs/`, fuera del repositorio), una línea JSON por evento:

- `request.log`: todas las solicitudes (método, ruta, estado, duración, IP).
- `error.log`: los errores devueltos por la API; los 500 incluyen el traceback.

Nunca se registran cuerpos ni encabezados (contraseñas, tokens).

## Variables de entorno

Ver `.env.example`. El `.env` solo existe en el servidor.

| Variable           | Por defecto (desarrollo)                                     |
| ------------------ | ------------------------------------------------------------ |
| `ENV`              | `development` (`production` en el servidor)                  |
| `DATABASE_URL`     | `postgresql+psycopg://trama:trama_dev@localhost:5432/trama`  |
| `JWT_SECRET`       | clave de desarrollo; **obligatoria** con `ENV=production`    |
| `JWT_EXPIRES_DAYS` | `7`                                                          |
| `CORS_ORIGINS`     | `["http://localhost:5173"]`                                  |
| `LOG_DIR`          | `logs`                                                       |
| `HOST` / `PORT`    | `127.0.0.1` / `3000`                                         |

## Despliegue (resumen)

1. En el servidor: Python 3.12, PostgreSQL y nginx. Crea el usuario y la base con una contraseña fuerte.
2. Clona el repositorio, crea el entorno virtual e instala `requirements.txt`.
3. Crea `.env` a partir de `.env.example` (`ENV=production`, `JWT_SECRET` nuevo, `DATABASE_URL`, `CORS_ORIGINS` con el dominio del frontend).
4. `alembic upgrade head`.
5. Servicio `systemd` (o `pm2`) que ejecute `.venv/bin/python -m app start` en el directorio del proyecto.
6. nginx como proxy de `api.<dominio>` hacia `127.0.0.1:3000` y certificado HTTPS con `certbot --nginx`.
