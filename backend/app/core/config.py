"""Configuración de la aplicación, leída exclusivamente de variables de entorno."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Contraseñas de ejemplo que nunca deben usarse fuera de desarrollo local.
_INSECURE_DEFAULT_PASSWORDS = {"", "CHANGE_ME_LOCAL_ONLY", "postgres", "password"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "db"
    postgres_port: int = 5432

    backend_cors_origins: str = ""

    # Resuelto por FakeCurrentUserProvider si no se envía la cabecera
    # X-Dev-User-Id. Sin efecto alguno en production (el proveedor
    # simulado se rechaza antes de leer este valor).
    dev_default_user_id: str | None = None

    pagination_default_limit: int = 20
    pagination_max_limit: int = 100

    # --- Audio (Fase 5) ---
    audio_storage_provider: str = "local"
    audio_storage_local_dir: str = "/app/storage/audio"
    audio_max_size_mb: int = 50
    audio_allowed_mime_types: str = (
        "audio/mpeg,audio/wav,audio/x-wav,audio/mp4,audio/webm,audio/ogg"
    )
    audio_allowed_extensions: str = "mp3,wav,m4a,ogg,webm"
    audio_max_duration_seconds: int = 3600

    # --- Transcripción (Fase 5) ---
    # Selección de proveedor únicamente por configuración — ver
    # app/integrations/factory.py. "mock" no requiere credenciales.
    transcription_provider: Literal["mock", "assemblyai"] = "mock"
    assemblyai_api_key: str | None = None
    assemblyai_base_url: str = "https://api.assemblyai.com"
    assemblyai_language_code: str = "es"
    assemblyai_poll_interval_seconds: float = 2.0
    assemblyai_poll_timeout_seconds: float = 120.0

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def audio_allowed_mime_types_list(self) -> list[str]:
        return [v.strip() for v in self.audio_allowed_mime_types.split(",") if v.strip()]

    @property
    def audio_allowed_extensions_list(self) -> list[str]:
        return [v.strip().lower() for v in self.audio_allowed_extensions.split(",") if v.strip()]

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _validate_production_safety(self) -> Settings:
        if not self.is_production:
            return self
        if not self.cors_origins or "*" in self.cors_origins:
            raise ValueError(
                "BACKEND_CORS_ORIGINS no puede estar vacío ni contener '*' en production."
            )
        if self.postgres_password in _INSECURE_DEFAULT_PASSWORDS:
            raise ValueError("POSTGRES_PASSWORD insegura para un entorno de production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
