"""Configuración de la aplicación, leída exclusivamente de variables de entorno."""

from __future__ import annotations

from decimal import Decimal
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
    transcription_provider: Literal["mock", "assemblyai", "deepgram"] = "mock"
    assemblyai_api_key: str | None = None
    assemblyai_base_url: str = "https://api.assemblyai.com"
    assemblyai_language_code: str = "es"
    assemblyai_poll_interval_seconds: float = 2.0
    assemblyai_poll_timeout_seconds: float = 120.0

    # --- Deepgram (Fase 5.3) ---
    deepgram_api_key: str | None = None
    # Endpoint EU (api.eu.deepgram.com) por defecto, no el genérico
    # api.deepgram.com: decisión deliberada para un producto sanitario —
    # residencia de datos dentro de la UE, GA y oficialmente documentada
    # (mismas credenciales, sin coste ni activación adicional) — ver
    # docs/transcription-benchmark.md §Endpoint europeo.
    deepgram_base_url: str = "https://api.eu.deepgram.com"
    deepgram_language_code: str = "es"
    deepgram_model: str = "nova-3"
    deepgram_timeout_seconds: float = 120.0
    # Perfil "deepgram_nova3_keyterms" (preparado, no llamado en la Fase
    # 5.3 — ver docs/transcription-benchmark.md §Configuración inicial).
    deepgram_keyterms_enabled: bool = False

    # --- Pricing del benchmark (Fase 5.1/5.2) — ver app/integrations/pricing.py ---
    # `None` en cada campo -> se usa el valor verificado por defecto de
    # pricing.py. Nunca facturación autoritativa: verifica el precio
    # vigente del proveedor antes de confiar en estas cifras.
    assemblyai_price_per_hour_usd: Decimal | None = None
    assemblyai_diarization_addon_per_hour_usd: Decimal | None = None
    assemblyai_medical_mode_addon_per_hour_usd: Decimal | None = None
    assemblyai_keyterms_addon_per_hour_usd: Decimal | None = None

    # --- Perfil experimental AssemblyAI (Fase 5.2) ---
    # Solo afecta al perfil "assemblyai_optimized" del benchmark — nunca al
    # perfil "assemblyai"/"assemblyai_baseline" (producción/reproducible),
    # ver app/integrations/factory.py. Nombres de parámetro verificados
    # contra la documentación oficial de AssemblyAI, ver
    # docs/transcription-benchmark.md §Inspección de la API.
    assemblyai_optimized_speech_model: str = "universal-3-5-pro"
    # `speakers_expected`: introduce conocimiento a priori del número de
    # hablantes — válido para una consulta audioprotésica típica
    # profesional↔paciente, NUNCA una suposición global del producto
    # (pueden existir acompañantes o varios profesionales). `None` lo
    # desactiva sin tocar código. AssemblyAI ignora este parámetro en
    # audios de menos de 2 minutos (ver docs/transcription-benchmark.md).
    assemblyai_optimized_speakers_expected: int | None = 2
    assemblyai_optimized_medical_mode: bool = True
    assemblyai_optimized_keyterms_enabled: bool = True

    # --- Pricing Deepgram (Fase 5.3) — ver app/integrations/pricing.py ---
    # Nunca mezclado con el pricing de AssemblyAI (funciones y campos
    # independientes).
    deepgram_price_per_minute_usd: Decimal | None = None
    deepgram_diarization_addon_per_minute_usd: Decimal | None = None
    deepgram_keyterm_addon_per_minute_usd: Decimal | None = None

    # --- Consentimiento de procesamiento IA (Fase 6, hito 6.0) ---
    # `False` en esta fase: todos los proveedores de `run_pipeline` siguen
    # siendo Mock (ver docs/fase-6-rfc.md §6.1) — activarlo no cambia
    # ningún test existente. El hito 6.3 (proveedor LLM real) decide su
    # activación en producción — ver docs/ai-pipeline-architecture.md §7.3.
    ai_processing_consent_enforced: bool = False
    ai_processing_consent_version: str = "1.0"

    # --- Límite duro de coste LLM por sesión (Fase 6, hito 6.1) ---
    # `False` en esta fase: sin proveedor real, `MockCostEstimator`
    # siempre devuelve 0 y el límite nunca se alcanzaría de todos modos —
    # ver docs/fase-6-rfc.md §6.3. Activarlo no cambia ningún test
    # existente. Debe poder desactivarse explícitamente en
    # development/test (encargo de la Fase 6.1, punto 9).
    llm_cost_limit_enforced: bool = False
    max_llm_cost_per_session_usd: Decimal | None = None
    # Techo de tokens de salida usado SOLO para la estimación "peor caso
    # razonable" previa a la llamada (§6.3) — nunca un límite real de
    # generación, un proveedor puede devolver menos o más.
    llm_max_output_tokens_estimate: int = 2000
    # Reintentos automáticos acotados (§5.5) — máximo total, el step
    # decide cuántos de esos corresponden a cada motivo de fallo.
    ai_pipeline_max_general_retries: int = 2
    ai_pipeline_max_regenerative_retries: int = 1
    ai_pipeline_retry_backoff_base_seconds: float = 0.0

    # --- Benchmark de generación LLM (Fase 6.2) — ver docs/generation-benchmark.md ---
    # OpenRouter es EXCLUSIVO de `benchmark/generation/` (RFC v2 §6.1): la
    # app productiva arranca sin `OPENROUTER_API_KEY` configurada — solo
    # `benchmark.generation` la lee, y falla explícitamente (nunca en
    # silencio) si se le pide ejecutar sin ella. Nunca se convierte en
    # `LanguageModelProvider` productivo en este hito.
    generation_benchmark_enabled: bool = False
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: float = 120.0

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
