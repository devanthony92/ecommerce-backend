import time

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.errors import register_error_handlers
from app.logging_config import request_logger, setup_logging
from app.routers import auth, inspirations, users


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_dir)

    # La documentación interactiva (/docs) solo fuera de producción.
    app = FastAPI(
        title="Trama API",
        version="0.1.0",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next) -> Response:
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            # Nunca se registran cuerpos ni encabezados (contraseñas, tokens).
            request_logger.info(
                "request",
                extra={
                    "data": {
                        "method": request.method,
                        "path": request.url.path,
                        "status": status_code,
                        "durationMs": round((time.perf_counter() - start) * 1000, 1),
                        "ip": request.client.host if request.client else None,
                    }
                },
            )

    register_error_handlers(app)

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(inspirations.router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
