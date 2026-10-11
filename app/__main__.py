"""Arranque de la API, equivalente a los scripts `dev` y `start` de npm.

python -m app dev     # desarrollo, con recarga automática
python -m app start   # producción, sin recarga
python -m app seed    # carga o actualiza el catálogo (--demo: cuentas de prueba)
"""

import argparse

import uvicorn

from app.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app")
    parser.add_argument("mode", choices=["dev", "start", "seed"])
    parser.add_argument("--demo", action="store_true", help="seed: crea las cuentas de prueba")
    args = parser.parse_args()
    settings = get_settings()

    if args.mode == "seed":
        from app.database import SessionLocal
        from app.seed import load_catalog
        from app.seed.demo import load_demo

        with SessionLocal() as db:
            categories, products, variants = load_catalog(db)
            print(f"Catálogo: {categories} categorías, {products} productos, {variants} variantes.")
            if args.demo:
                created = load_demo(db)
                print(
                    "Cuentas de prueba creadas." if created else "Las cuentas de prueba ya existen."
                )
    elif args.mode == "dev":
        uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
    else:
        # Detrás de nginx: confía en X-Forwarded-For solo si viene de la propia máquina.
        uvicorn.run(
            "app.main:app",
            host=settings.host,
            port=settings.port,
            workers=2,
            proxy_headers=True,
            forwarded_allow_ips="127.0.0.1",
        )


if __name__ == "__main__":
    main()
