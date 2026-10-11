from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Solo para desarrollo: en producción la app no arranca si JWT_SECRET no se cambió.
DEV_JWT_SECRET = "dev-secret-no-usar-en-produccion"


class Settings(BaseSettings):
    """Configuración desde variables de entorno (o .env en el servidor).

    En desarrollo todo tiene un valor por defecto: la API funciona sin .env.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["development", "production", "test"] = "development"
    database_url: str = "postgresql+psycopg://trama:trama_dev@localhost:5432/trama"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_expires_days: int = 7
    cors_origins: list[str] = ["http://localhost:5173"]
    log_dir: str = "logs"
    # URL pública del frontend y de esta API (retornos y webhook de Mercado Pago).
    frontend_url: str = "http://localhost:5173"
    api_url: str = "http://localhost:3000"
    # Mercado Pago (Checkout Pro). Sin token, el pago se simula y se aprueba al instante.
    mp_access_token: str | None = None
    mp_webhook_secret: str | None = None
    host: str = "127.0.0.1"
    port: int = 3000

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @model_validator(mode="after")
    def require_secret_in_production(self) -> "Settings":
        if self.is_production and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET es obligatorio en producción.")
        # Sin la clave del webhook no se puede comprobar que un aviso de pago sea de Mercado Pago.
        if self.mp_access_token and not self.mp_webhook_secret:
            raise ValueError("MP_WEBHOOK_SECRET es obligatorio si se configura MP_ACCESS_TOKEN.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
