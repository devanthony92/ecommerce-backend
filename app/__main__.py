"""Arranque de la API, equivalente a los scripts `dev` y `start` de npm.

python -m app dev     # desarrollo, con recarga automática
python -m app start   # producción, sin recarga
"""

import argparse

import uvicorn

from app.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app")
    parser.add_argument("mode", choices=["dev", "start"])
    args = parser.parse_args()
    settings = get_settings()

    if args.mode == "dev":
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
