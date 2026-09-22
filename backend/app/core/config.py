"""Configuración de la aplicación, leída exclusivamente de variables de entorno."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.field_encryption import FieldEncryptionError, parse_keys_env

# Contraseñas de ejemplo que nunca deben usarse fuera de desarrollo local.
_INSECURE_DEFAULT_PASSWORDS = {"", "CHANGE_ME_LOCAL_ONLY", "postgres", "password"}

#: Los tres campos de routing estático por artifact_type (Fase 6.3) — ver
#: `_validate_production_safety`. Nombre de campo, no de vendor: cada uno
#: se lee con `getattr` para saber si ese artifact_type usa un proveedor
#: real (`!= "mock"`).
_LLM_ROUTING_FIELDS = (
    "llm_provider_summary",
    "llm_provider_patient_summary",
    "llm_provider_missing_information",
    # Ampliación 2026-09-21 (docs/clinical-safety.md §7): CLINICAL_FLAGS
    # reabre la decisión de "sin LLM" con un generador real DISPONIBLE
    # pero apagado por defecto ("mock") — mismo criterio de production
    # safety que los tres anteriores en cuanto se active para cualquier
    # clínica: consentimiento y límite de coste ya activos, y clave de
    # API del vendor configurada.
    "llm_provider_clinical_flags",
)
#: Vendor -> nombre del campo de `Settings` que guarda su API key — una
#: sola key por vendor, nunca duplicada por artifact_type.
_VENDOR_API_KEY_FIELDS = {
    "anthropic": "anthropic_api_key",
    "openai": "openai_api_key",
    "google": "google_api_key",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Un fallback `${VAR:-}` vacío en docker-compose.yml (para campos
        # opcionales sin valor natural en desarrollo, p. ej.
        # MAX_LLM_COST_PER_SESSION_USD) pasa una cadena vacía al contenedor
        # si el operador no la define en su .env — sin esto, pydantic
        # intenta parsear "" como Decimal/bool/Literal y el arranque entero
        # falla. Tratar "" como "no definida" dejar caer al default de
        # Python es el comportamiento correcto, no un valor real.
        env_ignore_empty=True,
    )

    environment: Literal["development", "test", "production", "staging"] = "development"
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

    # --- Autenticación (Fase 9, hito 9.1) ---
    # "fake" (por defecto) no cambia nada del comportamiento actual: sigue
    # resolviendo `get_current_user_provider()` a `FakeCurrentUserProvider`
    # (X-Dev-User-Id). "real" lo resuelve a `RealCurrentUserProvider` (JWT
    # Bearer, ver core/current_user.py) — obligatorio en production, ver
    # `_validate_production_safety`.
    auth_mode: Literal["fake", "real"] = "fake"
    # Clave de firma HS256 del JWT emitido por `AuthService.login`
    # (app/auth/service.py) y verificado por `RealCurrentUserProvider`.
    # Requerida siempre (igual que `postgres_password`): sin ella no
    # arranca ni siquiera en development/test — ver
    # tests/conftest.py para el valor de test.
    jwt_secret_key: str

    pagination_default_limit: int = 20
    pagination_max_limit: int = 100

    # --- Exportación longitudinal de historia clínica (Fase 6.7, hito 6.7.4) ---
    # Techo de sesiones por exportación scope=patient — independiente de
    # `pagination_max_limit` (paginación de la vista JSON): mezclarlos
    # produciría dos guardarraíles contradictorios para dos operaciones
    # distintas (ver docs/fase-6-rfc.md §7.2). Sin proveedor real de por
    # medio, 50 es un valor conservador y explícito para no generar
    # documentos desmedidos en memoria; ajustable por entorno.
    clinical_record_export_max_sessions: int = Field(default=50, gt=0)

    # --- Audio (Fase 5) ---
    audio_storage_provider: str = "local"
    audio_storage_local_dir: str = "storage/audio"
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

    # --- Proveedores LLM directos por artifact_type (Fase 6.3) ---
    # Routing ESTÁTICO por artifact_type, resuelto por configuración — nunca
    # una constante Python (docs/fase-6-rfc.md §6.1/§11.1 decisión 12: "no
    # existe global_winner", cada artifact_type usa su proveedor ganador).
    # Sin selección dinámica por sesión/paciente/coste/latencia, sin
    # fallback automático entre proveedores, sin OpenRouter en producción
    # (exclusivo de `benchmark/generation/`, ver más abajo). "mock" (valor
    # por defecto en los tres) es la configuración segura de
    # development/test — activar un proveedor real es una decisión
    # explícita por entorno, nunca el comportamiento por defecto.
    llm_provider_summary: Literal["mock", "anthropic", "openai", "google"] = "mock"
    llm_model_summary: str | None = None
    llm_provider_patient_summary: Literal["mock", "anthropic", "openai", "google"] = "mock"
    llm_model_patient_summary: str | None = None
    llm_provider_missing_information: Literal["mock", "anthropic", "openai", "google"] = "mock"
    llm_model_missing_information: str | None = None
    # Ampliación 2026-09-21 (docs/clinical-safety.md §7, reapertura de la
    # decisión "sin LLM"): mismo patrón que los tres anteriores, pero
    # "mock" (el checklist de reglas, MockClinicalFlagsGenerator) sigue
    # siendo el valor por defecto en TODOS los entornos, incluida
    # production — activar un valor distinto de "mock" aquí para
    # cualquier clínica real requiere primero la validación clínica y
    # legal que ese documento exige, nunca solo un cambio de variable de
    # entorno sin más.
    llm_provider_clinical_flags: Literal["mock", "anthropic", "openai", "google"] = "mock"
    llm_model_clinical_flags: str | None = None

    # Una API key por vendor, nunca duplicada por artifact_type — los tres
    # routings de arriba pueden compartir el mismo vendor sin repetir
    # credenciales. `base_url`/`timeout_seconds` con el mismo patrón que
    # `assemblyai_*`/`deepgram_*` (Fase 5). IDs de modelo NUNCA se fijan
    # aquí como default: se completan en el hito 6.3.5 tras verificar el
    # identificador nativo exacto contra la documentación oficial vigente
    # de cada proveedor — los IDs de la Fase 6.2 son de OpenRouter, no
    # necesariamente válidos contra la API directa (ver docs/fase-6-rfc.md
    # §11.2).
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_timeout_seconds: float = 120.0
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: float = 120.0
    google_api_key: str | None = None
    google_base_url: str = "https://generativelanguage.googleapis.com"
    google_timeout_seconds: float = 120.0

    # --- Retención (Fase 7.2 / hito 10.4) ---
    # Umbral global vía entorno, no configurable por clínica (fuera de
    # alcance de esta fase, ver docs/development-plan.md §Fase 7).
    retention_days_default: int = Field(default=30, gt=0)
    # Autentica al LLAMADOR de POST /api/v1/retention/system-purge (un cron
    # externo), no a un usuario de una clínica concreta — mismo patrón que
    # `jwt_secret_key`: obligatorio, sin default, no arranca ni siquiera en
    # development/test sin él (ver tests/conftest.py). El endpoint la
    # compara con `secrets.compare_digest`, nunca `==` (ver
    # app/retention/api/router.py).
    retention_cron_secret: str

    # --- Hardening HTTP (Fase 10.5) ---
    # Techo a nivel de aplicación, POR ENCIMA de `audio_max_size_mb` (que
    # valida específicamente el tamaño de audio subido): rechaza cualquier
    # cuerpo de request anormalmente grande antes de procesarlo, en
    # cualquier endpoint — ver app/core/request_size_limit.py.
    max_request_body_mb: int = Field(default=60, gt=0)

    # --- Error tracking (Fase 10.6) — ver app/core/sentry.py ---
    # Opcional, sin default: si no está configurada, Sentry no se
    # inicializa en ningún entorno (ni siquiera production) — no forma
    # parte de `_validate_production_safety`, a diferencia de
    # `jwt_secret_key`/`retention_cron_secret`, porque su ausencia nunca
    # compromete la seguridad, solo la observabilidad.
    sentry_dsn: str | None = None

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

    # --- Onboarding self-service multi-clínica (Fase 12, hito 12.1) ---
    # Ver docs/fase-12-rfc.md. Nunca datos de pacientes: solo contacto de
    # personal de clínica (registro, verificación de email, recuperación
    # de contraseña).
    # URL pública del frontend — usada para construir el enlace que el
    # usuario recibe por email (`{frontend_base_url}/verify-email?token=`,
    # `{frontend_base_url}/reset-password?token=`). Nunca generado por el
    # cliente: siempre desde esta configuración de servidor.
    frontend_base_url: str = "http://localhost:5173"
    # Vida del token de verificación de email (link enviado al registrarse).
    email_verification_token_ttl_hours: int = Field(default=24, gt=0)
    # Vida del token de recuperación de contraseña — deliberadamente más
    # corta que la de verificación: una petición de reseteo no solicitada
    # que quede sin usar debe caducar antes.
    password_reset_token_ttl_hours: int = Field(default=2, gt=0)
    # --- Invitaciones a compañeros de clínica (Fase 12, hito 12.2) ---
    # En días, no horas (a diferencia de los dos anteriores): una
    # invitación a un compañero es una decisión de gestión de equipo, con
    # un horizonte de "aceptación" natural más largo que confirmar el
    # propio email o resetear la propia contraseña — 7 días por defecto,
    # ver docs/fase-12-rfc.md §5.
    invitation_token_ttl_days: int = Field(default=7, gt=0)

    # --- Email transaccional (Fase 12, hito 12.1) — ver app/integrations/factory.py ---
    # "mock" (por defecto, `ConsoleEmailSender`) no requiere credenciales y
    # nunca envía tráfico real (CLAUDE.md §6). "brevo": elegido en
    # docs/fase-12-rfc.md §5, DPA autoservicio archivado en
    # docs/legal/brevo-dpa-2026-09-15.pdf.
    email_provider: Literal["mock", "brevo"] = "mock"
    email_from_address: str = "no-reply@audiology-assistant.dev"
    email_from_name: str = "Audiology AI Assistant"
    brevo_api_key: str | None = None
    brevo_base_url: str = "https://api.brevo.com"
    brevo_timeout_seconds: float = 30.0

    # --- Anti-abuso en el alta pública (Fase 12, hito 12.4 ampliado) ---
    # Decidido con Gerard el 2026-09-18: `POST /clinics/signup` es
    # superficie pública sin autenticar (mismo riesgo que login/onboarding
    # en general), y el rate limiting de 5/minute (ver
    # app/core/rate_limit.py) no distingue tráfico automatizado de
    # humano. Turnstile filtra scripts/bots genéricos; el bloqueo de
    # dominios de email desechables cubre el abuso humano que Turnstile no
    # detiene (una persona real usando un email de usar-y-tirar para
    # crear cuentas de prueba repetidas). "mock" (por defecto,
    # `MockTurnstileVerifier`) siempre aprueba y no requiere credenciales
    # ni hace ninguna llamada real (CLAUDE.md §6) — igual que
    # `email_provider`/`transcription_provider`. "cloudflare": única
    # opción real, ver
    # app/integrations/providers/cloudflare_turnstile_verifier.py.
    turnstile_provider: Literal["mock", "cloudflare"] = "mock"
    turnstile_secret_key: str | None = None
    turnstile_base_url: str = "https://challenges.cloudflare.com"
    turnstile_timeout_seconds: float = 10.0

    # --- Limpieza de clínicas no verificadas (Fase 12, hito 12.4) ---
    # Una clínica es "fantasma" si ninguno de sus usuarios está activo
    # (nunca verificó su email tras `POST /clinics/signup`, ver
    # `UnverifiedClinicCleanupService`) y fue creada hace más de este
    # número de días — decidido con Gerard el 2026-09-15: suficiente
    # margen para reintentar la verificación (el enlace en sí caduca a las
    # `email_verification_token_ttl_hours`, mucho antes) sin acumular
    # basura mucho tiempo.
    unverified_clinic_ttl_days: int = Field(default=7, gt=0)
    # Autentica al LLAMADOR de POST /api/v1/onboarding/system-cleanup (un
    # cron externo), no a un usuario de una clínica concreta — mismo
    # patrón que `retention_cron_secret`: obligatorio, sin default, no
    # arranca ni siquiera en development/test sin él (ver
    # tests/conftest.py). Secreto propio, no reutiliza
    # `retention_cron_secret`: son dos trabajos de sistema independientes,
    # cada uno con su propio cron en el entorno de despliegue real (ver
    # ops/onboarding-cleanup-cron/), y compartir secreto acoplaría su
    # rotación sin necesidad. El endpoint la compara con
    # `secrets.compare_digest`, nunca `==` (ver
    # app/onboarding/api/router.py).
    onboarding_cleanup_cron_secret: str

    # --- Facturación / Stripe (Fase 13, hito 13.1) — ver docs/fase-13-rfc.md ---
    # "mock" (por defecto, `MockPaymentGateway`) nunca llama a Stripe de
    # verdad — mismo criterio de CLAUDE.md §6 que `transcription_provider`/
    # `email_provider`/`turnstile_provider`. "stripe" es el único proveedor
    # real. Alcance de este hito: solo `create_checkout_session` y el
    # webhook con los eventos de alta (`checkout.session.completed`) — el
    # gate de acceso por `subscription_status` (hito 13.2) y
    # `create_portal_session` (hito 13.3) quedan para hitos posteriores, ver
    # docs/fase-13-rfc.md §7.
    payment_gateway: Literal["mock", "stripe"] = "mock"
    stripe_secret_key: str | None = None
    # Verifica la firma `Stripe-Signature` de `POST /billing/webhook` — sin
    # ella, `StripePaymentGateway.construct_webhook_event` rechaza
    # cualquier payload (nunca confía en el cuerpo del request sin
    # verificar la firma primero, ver docs/fase-13-rfc.md §6).
    stripe_webhook_secret: str | None = None
    # Un Price de Stripe (modo suscripción) por nivel — ver la tabla de
    # precios cerrada en docs/fase-13-rfc.md §3.2. El nivel Cadena/Empresa
    # se gestiona semi-manualmente por Gerard (§3.3): su Price de volumen
    # también se resuelve desde aquí una vez creado en el dashboard de
    # Stripe.
    stripe_price_id_basico: str | None = None
    stripe_price_id_profesional: str | None = None
    stripe_price_id_clinica_grande: str | None = None
    stripe_price_id_cadena_empresa: str | None = None

    # --- Facturación / Stripe (Fase 13, hito 13.2) — resto de ciclo de vida,
    # overage y reconciliación, ver docs/fase-13-rfc.md §3.2/§5 ---
    # Price MEDIDO (metered, modo "set" de usage record) por nivel, usado
    # por `BillingService.report_overage_usage` para cobrar el exceso sobre
    # `estimated_cost_usd` cuando una clínica supera el tope incluido de
    # sesiones/mes. Solo los niveles con tope definido lo tienen — ver
    # `app/billing/domain/plans.py::PLAN_INCLUDED_SESSIONS` (Cadena/Empresa
    # queda fuera a propósito, sin tope ni overage en este hito).
    stripe_metered_price_id_basico: str | None = None
    stripe_metered_price_id_profesional: str | None = None
    stripe_metered_price_id_clinica_grande: str | None = None
    # `event_name` del Stripe Billing Meter de cada nivel — objeto DISTINTO
    # del Price medido de arriba (ver docstring de
    # `PaymentGateway.report_overage_usage`): el Price se usa al crear la
    # Checkout Session, el Meter al reportar uso. El Meter debe crearse en
    # Stripe con fórmula de agregación "last", no "sum" — de lo contrario
    # el overage reportado cada día por el cron de reconciliación se
    # acumularía sobre sí mismo en vez de sustituir el total del periodo.
    stripe_meter_event_name_basico: str | None = None
    stripe_meter_event_name_profesional: str | None = None
    stripe_meter_event_name_clinica_grande: str | None = None
    # `estimated_cost_usd` (lo que cobran las APIs de LLM/transcripción,
    # ver Fase 6) está siempre en USD, pero la Price MEDIDA de Stripe de
    # Gerard está denominada en EUR (mismo criterio que el resto de Prices
    # del catálogo — ver `stripe_price_id_<nivel>`). Sin esta conversión,
    # `report_overage_usage` reportaría el mismo número de céntimos pero
    # Stripe los facturaría como céntimos de EUR, no de USD. Tipo de cambio
    # ESTÁTICO fijado a mano (sin integración con ninguna API de divisas en
    # este hito) — aproximado a propósito, Gerard debe revisarlo y
    # actualizarlo periódicamente; ver docs/development-plan.md, Fase 13,
    # hito 13.2.
    usd_to_eur_exchange_rate: Decimal = Decimal("0.92")
    # Autentica al LLAMADOR de POST /api/v1/billing/reconcile (un cron
    # externo diario, ver ops/billing-reconciliation-cron/) — mismo patrón
    # que `retention_cron_secret`/`onboarding_cleanup_cron_secret`:
    # obligatorio, sin default, secreto propio (no reutiliza los otros dos:
    # son tres trabajos de sistema independientes). El endpoint la compara
    # con `secrets.compare_digest`, nunca `==`.
    billing_reconcile_cron_secret: str

    # --- Cifrado de campos a nivel de aplicación (Fase 12) — añadido 2026-09-18 ---
    # Ver app/core/field_encryption.py y docs/privacy-and-security.md §4.
    # Diseño con claves VERSIONADAS desde el principio, no una clave fija de
    # "MVP": formato "key_id:base64key,key_id:base64key,..." — cada clave
    # debe decodificar a exactamente 32 bytes (AES-256). Obligatorio en
    # TODOS los entornos (igual que jwt_secret_key): ai_artifact_versions.
    # content es NOT NULL y pasa por EncryptedJSON, así que ni siquiera
    # development/test pueden arrancar sin esto configurado. Nunca se
    # retira una clave de aquí hasta haber re-cifrado con ella todo lo que
    # la usaba — ver app/core/field_encryption_cli.py.
    field_encryption_keys: str
    # Qué key_id de field_encryption_keys se usa para CIFRAR valores
    # nuevos — las demás claves presentes siguen sirviendo para DESCIFRAR
    # valores antiguos (rotación sin tiempo de inactividad).
    field_encryption_active_key_id: str

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_staging(self) -> bool:
        return self.environment == "staging"

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
        if not (self.is_production or self.is_staging):
            return self
        if not self.cors_origins or "*" in self.cors_origins:
            raise ValueError(
                "BACKEND_CORS_ORIGINS no puede estar vacío ni contener '*' en production."
            )
        if self.postgres_password in _INSECURE_DEFAULT_PASSWORDS:
            raise ValueError("POSTGRES_PASSWORD insegura para un entorno de production.")
        if self.jwt_secret_key in _INSECURE_DEFAULT_PASSWORDS:
            raise ValueError("JWT_SECRET_KEY insegura para un entorno de production.")
        if self.retention_cron_secret in _INSECURE_DEFAULT_PASSWORDS:
            raise ValueError("RETENTION_CRON_SECRET insegura para un entorno de production.")
        if self.onboarding_cleanup_cron_secret in _INSECURE_DEFAULT_PASSWORDS:
            raise ValueError(
                "ONBOARDING_CLEANUP_CRON_SECRET insegura para un entorno de production."
            )
        if self.billing_reconcile_cron_secret in _INSECURE_DEFAULT_PASSWORDS:
            raise ValueError(
                "BILLING_RECONCILE_CRON_SECRET insegura para un entorno de production."
            )
        if (
            self.field_encryption_keys in _INSECURE_DEFAULT_PASSWORDS
            or not self.field_encryption_keys.strip()
        ):
            raise ValueError(
                "FIELD_ENCRYPTION_KEYS insegura o vacía para un entorno de production: el "
                "contenido clínico más sensible (ai_artifact_versions.content, entre otros) "
                "depende de este cifrado — ver docs/privacy-and-security.md §4."
            )
        if (
            self.field_encryption_active_key_id in _INSECURE_DEFAULT_PASSWORDS
            or not self.field_encryption_active_key_id.strip()
        ):
            raise ValueError("FIELD_ENCRYPTION_ACTIVE_KEY_ID insegura o vacía en production.")
        try:
            field_encryption_keys_map = parse_keys_env(self.field_encryption_keys)
        except FieldEncryptionError as exc:
            raise ValueError(f"FIELD_ENCRYPTION_KEYS inválido en production: {exc}") from exc
        if self.field_encryption_active_key_id not in field_encryption_keys_map:
            raise ValueError(
                "FIELD_ENCRYPTION_ACTIVE_KEY_ID no aparece dentro de FIELD_ENCRYPTION_KEYS."
            )
        if any(len(key_bytes) != 32 for key_bytes in field_encryption_keys_map.values()):
            raise ValueError(
                "Todas las claves de FIELD_ENCRYPTION_KEYS deben decodificar a 32 bytes "
                "(AES-256)."
            )
        if self.auth_mode != "real":
            # Fase 9, hito 9.1: `FakeCurrentUserProvider` (X-Dev-User-Id)
            # ya se rechaza por su cuenta en production (ver
            # core/current_user.py), pero ese fallo solo ocurre en el
            # primer uso de `get_current_user_provider()`. Este chequeo
            # falla más pronto, en el arranque, igual que el resto de
            # guardarraíles de production de este método.
            raise ValueError(
                "AUTH_MODE debe ser 'real' en production: FakeCurrentUserProvider "
                "(X-Dev-User-Id) no es un mecanismo de autenticación válido."
            )

        active_vendors = {
            getattr(self, field) for field in _LLM_ROUTING_FIELDS if getattr(self, field) != "mock"
        }
        if active_vendors:
            # Fase 6.3, encargo §7: production con cualquier artifact_type
            # en un proveedor real exige consentimiento y límite de coste
            # ya activos — nunca tráfico de pago sin ambos guardarraíles.
            if not self.ai_processing_consent_enforced:
                raise ValueError(
                    "AI_PROCESSING_CONSENT_ENFORCED debe ser true en production: hay al "
                    "menos un artifact_type configurado con un proveedor LLM real."
                )
            if not self.llm_cost_limit_enforced:
                raise ValueError(
                    "LLM_COST_LIMIT_ENFORCED debe ser true en production: hay al menos un "
                    "artifact_type configurado con un proveedor LLM real."
                )
            if self.max_llm_cost_per_session_usd is None or self.max_llm_cost_per_session_usd <= 0:
                raise ValueError(
                    "MAX_LLM_COST_PER_SESSION_USD debe tener un valor positivo en production: "
                    "hay al menos un artifact_type configurado con un proveedor LLM real."
                )
            missing_key_vars = sorted(
                _VENDOR_API_KEY_FIELDS[vendor].upper()
                for vendor in active_vendors
                if not getattr(self, _VENDOR_API_KEY_FIELDS[vendor])
            )
            if missing_key_vars:
                raise ValueError(
                    "Faltan claves de API para los proveedores LLM configurados en "
                    f"production: {', '.join(missing_key_vars)}."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
