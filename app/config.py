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
    host: str = "127.0.0.1"
    port: int = 3000

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @model_validator(mode="after")
    def require_secret_in_production(self) -> "Settings":
        if self.is_production and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET es obligatorio en producción.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
