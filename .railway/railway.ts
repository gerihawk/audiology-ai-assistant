import { bucket, defineRailway, github, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("Postgres", { region: "ams" });
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "ams", sizeMB: 500 });
  const audiologyAiAssistantVolume = volume("audiology-ai-assistant-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "ams", sizeMB: 500 });
  const adaptableDrumEJAo = bucket("adaptable-drum-EJAo", { region: "ams" });
  const fearlessHeart = service("fearless-heart", {
    source: github("gerihawk/audiology-ai-assistant", { branch: "feature/phase-11-backups", checkSuites: false, rootDirectory: "ops/postgres-backup-cron" }),
    replicas: { "ams": 1 },
    deploy: { cronSchedule: "0 3 * * *", restartPolicyType: "NEVER" },
    env: { DATABASE_URL: preserve(), POSTGRES_BACKUP_ACCESS_KEY_ID: preserve(), POSTGRES_BACKUP_AGE_PUBLIC_KEY: preserve(), POSTGRES_BACKUP_BUCKET_ENDPOINT: preserve(), POSTGRES_BACKUP_BUCKET_NAME: preserve(), POSTGRES_BACKUP_SECRET_ACCESS_KEY: preserve() },
  });
  const truthfulSolace = service("truthful-solace", {
    source: github("gerihawk/audiology-ai-assistant", { branch: "feature/phase-10-deployment", checkSuites: false, rootDirectory: "/ops/retention-cron" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "/ops/retention-cron/Dockerfile" },
    replicas: { "ams": 1 },
    deploy: { cronSchedule: "0 3 * * *", restartPolicyType: "NEVER" },
    env: { RETENTION_CRON_SECRET: preserve(), RETENTION_PURGE_URL: preserve() },
  });
  const givingNourishment = service("giving-nourishment", {
    source: github("gerihawk/audiology-ai-assistant", { branch: "feature/phase-10-deployment", checkSuites: false, rootDirectory: "/frontend" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "/frontend/Dockerfile.prod" },
    replicas: { "ams": 1 },
    env: { AI_PROCESSING_CONSENT_ENFORCED: preserve(), AI_PROCESSING_CONSENT_VERSION: preserve(), ASSEMBLYAI_API_KEY: preserve(), ASSEMBLYAI_LANGUAGE_CODE: preserve(), AUTH_MODE: preserve(), BACKEND_CORS_ORIGINS: preserve(), BACKEND_PORT: preserve(), DEEPGRAM_API_KEY: preserve(), DEEPGRAM_BASE_URL: preserve(), DEEPGRAM_LANGUAGE_CODE: preserve(), DEEPGRAM_MODEL: preserve(), ENVIRONMENT: preserve(), FRONTEND_PORT: preserve(), GENERATION_BENCHMARK_ENABLED: preserve(), JWT_SECRET_KEY: preserve(), LOG_LEVEL: preserve(), OPENROUTER_API_KEY: preserve(), OPENROUTER_BASE_URL: preserve(), POSTGRES_DB: preserve(), POSTGRES_HOST: preserve(), POSTGRES_PASSWORD: preserve(), POSTGRES_PORT: preserve(), POSTGRES_USER: preserve(), TRANSCRIPTION_PROVIDER: preserve(), VITE_API_BASE_URL: preserve(), VITE_AUTH_MODE: preserve(), VITE_SENTRY_DSN: preserve(), VITE_SENTRY_ENVIRONMENT: preserve() },
  });
  const audiologyAiAssistant = service("audiology-ai-assistant", {
    source: github("gerihawk/audiology-ai-assistant", { branch: "feature/phase-10-deployment", checkSuites: false, rootDirectory: "/backend" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "backend/Dockerfile.prod" },
    start: "",
    replicas: { "ams": 1 },
    deploy: { preDeployCommand: ["alembic upgrade head"] },
    volumeMounts: { "/app/storage": audiologyAiAssistantVolume },
    env: { AI_PROCESSING_CONSENT_ENFORCED: preserve(), AI_PROCESSING_CONSENT_VERSION: preserve(), ANTHROPIC_API_KEY: preserve(), ASSEMBLYAI_API_KEY: preserve(), ASSEMBLYAI_LANGUAGE_CODE: preserve(), AUDIO_STORAGE_LOCAL_DIR: preserve(), AUTH_MODE: preserve(), BACKEND_CORS_ORIGINS: preserve(), BACKEND_PORT: preserve(), DEEPGRAM_API_KEY: preserve(), DEEPGRAM_BASE_URL: preserve(), DEEPGRAM_LANGUAGE_CODE: preserve(), DEEPGRAM_MODEL: preserve(), ENVIRONMENT: preserve(), FRONTEND_PORT: preserve(), GENERATION_BENCHMARK_ENABLED: preserve(), JWT_SECRET_KEY: preserve(), LLM_COST_LIMIT_ENFORCED: preserve(), LLM_MODEL_MISSING_INFORMATION: preserve(), LLM_MODEL_PATIENT_SUMMARY: preserve(), LLM_MODEL_SUMMARY: preserve(), LLM_PROVIDER_MISSING_INFORMATION: preserve(), LLM_PROVIDER_PATIENT_SUMMARY: preserve(), LLM_PROVIDER_SUMMARY: preserve(), LOG_LEVEL: preserve(), MAX_LLM_COST_PER_SESSION_USD: preserve(), OPENAI_API_KEY: preserve(), OPENROUTER_API_KEY: preserve(), OPENROUTER_BASE_URL: preserve(), POSTGRES_DB: preserve(), POSTGRES_HOST: preserve(), POSTGRES_PASSWORD: preserve(), POSTGRES_PORT: preserve(), POSTGRES_USER: preserve(), RETENTION_CRON_SECRET: preserve(), SENTRY_DSN: preserve(), TRANSCRIPTION_PROVIDER: preserve(), VITE_API_BASE_URL: preserve(), VITE_AUTH_MODE: preserve() },
  });

  return project("giving-friendship", {
    resources: [fearlessHeart, truthfulSolace, Postgres, givingNourishment, audiologyAiAssistant, postgresVolume, audiologyAiAssistantVolume, adaptableDrumEJAo],
  });
});
