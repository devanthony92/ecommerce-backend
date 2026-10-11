"""Manejo centralizado de errores.

Los controladores no arman respuestas de error: lanzan AppError y estos
handlers responden siempre con el mismo formato:

    {"error": {"code": "...", "message": "...", "details": {...} | null}}
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_config import error_logger


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def unauthorized(message: str = "Autorización requerida.") -> AppError:
    return AppError(401, "UNAUTHORIZED", message)


def forbidden(message: str) -> AppError:
    return AppError(403, "FORBIDDEN", message)


def not_found(message: str) -> AppError:
    return AppError(404, "NOT_FOUND", message)


def conflict(code: str, message: str, details: dict[str, str] | None = None) -> AppError:
    return AppError(409, code, message, details)


# Mensajes en español para los errores de validación de Pydantic.
def _validation_message(error: dict[str, Any]) -> str:
    kind = error["type"]
    ctx = error.get("ctx") or {}
    if kind == "missing":
        return "Campo obligatorio."
    if kind == "string_too_short":
        if ctx.get("min_length") == 1:
            return "Campo obligatorio."
        return f"Debe tener al menos {ctx.get('min_length')} caracteres."
    if kind == "string_too_long":
        return f"Debe tener como máximo {ctx.get('max_length')} caracteres."
    if kind == "value_error" and "email" in str(error.get("msg", "")).lower():
        return "Ingresa un correo válido."
    if kind.startswith("url"):
        return "Debe ser una URL válida (http o https)."
    if kind in ("int_parsing", "int_type", "int_from_float"):
        return "Debe ser un número entero."
    if kind == "greater_than":
        return f"Debe ser mayor que {ctx.get('gt')}."
    if kind in ("string_type", "model_attributes_type", "dict_type"):
        return "Tipo de dato no válido."
    if kind == "json_invalid":
        return "El cuerpo no es un JSON válido."
    return "Valor no válido."


def _field_name(loc: tuple[Any, ...]) -> str:
    # ("body", "email") → "email"; ("path", "inspiration_id") → "inspiration_id".
    parts = [str(part) for part in loc[1:]] or [str(loc[0])]
    return ".".join(parts)


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, str] | None = None,
) -> JSONResponse:
    error_logger.warning(
        message,
        extra={
            "data": {
                "method": request.method,
                "path": request.url.path,
                "status": status_code,
                "code": code,
                "message": message,
                "details": details,
            }
        },
    )
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )


HTTP_CODES = {
    404: ("NOT_FOUND", "El recurso solicitado no existe."),
    405: ("METHOD_NOT_ALLOWED", "Método no permitido."),
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(request, exc.status_code, exc.code, exc.message, exc.details)

    # Validación del cuerpo y de los parámetros: nunca llega al controlador.
    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details: dict[str, str] = {}
        for error in exc.errors():
            details.setdefault(_field_name(tuple(error["loc"])), _validation_message(error))
        return _error_response(
            request, 400, "VALIDATION_ERROR", "Revisa los datos enviados.", details
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, message = HTTP_CODES.get(exc.status_code, ("HTTP_ERROR", str(exc.detail)))
        return _error_response(request, exc.status_code, code, message)

    # Cualquier error no previsto: 500 sin filtrar detalles internos al cliente.
    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        error_logger.error(
            "Error no controlado",
            exc_info=exc,
            extra={"data": {"method": request.method, "path": request.url.path, "status": 500}},
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Error interno del servidor.",
                    "details": None,
                }
            },
        )
