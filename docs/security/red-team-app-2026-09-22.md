# Red team de la aplicación real — 2026-09-22

Combina el cierre de la **Fase 0** (AgentShield, superficie del propio tooling
de IA) con un red team de la **aplicación real** (backend FastAPI + frontend
React) sobre 8 áreas específicas del producto. Todo verificado contra código
real y, donde fue posible, contra comportamiento en vivo del stack Docker
local con datos ficticios — nada contra staging ni producción.

**Estado del `--fix` original de Fase 0:** el `agentshield scan --fix` (paso
2 del plan original) **nunca se ejecutó** — ni la CLI `agentshield` (no
existe) ni el modo `--fix` de `ecc-agentshield`. Lo que sí está aplicado y
comiteado (por el usuario, fuera de esta sesión de IA) son las correcciones
puntuales revisadas a mano: Regla 10 de CLAUDE.md, permisos de
`.claude/settings.local.json`, y el bump de dependencias (`pytest`,
`pytest-asyncio`, `black`, `vite`, `vitest`) — ver
[agentshield-2026-09-22.md](./agentshield-2026-09-22.md) para el detalle
completo de esa fase. Ningún hallazgo de las categorías A-D de esa fase
quedó marcado como corregido por el propio `--fix` automático porque ese
paso no llegó a correr.

**Metodología de esta fase:** 3 revisiones en profundidad en paralelo
(auth/multi-tenant; datos de paciente + pipeline de IA; facturación +
superficie API), cada una con lectura de código real y pruebas curl activas
contra `localhost:8000`/Postgres local con datos ficticios, más auditoría
directa de dependencias (`pip-audit`, `npm audit`) e infraestructura
(separación staging/production documentada en `docs/privacy-and-security.md`).
Una prueba de IDOR requirió crear una clínica/admin ficticios en la base
local (`REDTEAM Clinica B`) — ya limpiados (verificado, 0 filas).

---

## A. Bloqueante — antes de dar de alta al primer cliente real

### A1. `SafetyValidator` usa solo 3 frases fijas — evadible con cualquier reformulación
- **Estado (2026-09-23): mitigado.** Paso 1: patrones deterministas ampliados en `safety.py` (variantes, sinónimos, inglés), verificado sin falsos positivos contra fixtures/benchmark reales. Paso 2: capa LLM de auditoría **no bloqueante** (`LLM_PROVIDER_SAFETY_AUDIT`, apagada por defecto). `test_ai_pipeline_safety_validator::test_bypass_reformulaciones_no_detectadas_por_lista_literal` tiene los casos que solo cubriría una capa semántica activa marcados xfail estricto (2026-09-25): «hecho clínico presentado como establecido, sin usar ninguna de las 3 frases» (*"Hipoacusia neurosensorial bilateral confirmada mediante audiometría."*). Los otros 14 casos pasan. Activarla con proveedor real exige antes anotarlo en la EIPD (`docs/eipd-dpia.md`).
- **Dónde:** `backend/app/ai_pipeline/domain/safety.py:23-27` —
  `FORBIDDEN_CLINICAL_LANGUAGE = ("el paciente tiene", "diagnóstico confirmado", "tratamiento recomendado automáticamente")`.
  La normalización (líneas 55-61) solo tolera mayúsculas/tildes/puntuación.
- **Cómo reproducirlo:** un LLM que genere *"el paciente presenta una
  otitis"*, *"queda confirmado el diagnóstico de..."*, o el equivalente en
  inglés, pasa el validador sin ninguna alerta.
- **Impacto real:** es la **única barrera determinista** del pipeline contra
  lenguaje diagnóstico prohibido (Regla 2 de CLAUDE.md, docs/clinical-safety.md
  §3), invocada sin excepción en `steps/base.py`. Su fragilidad significa que
  un borrador de IA puede llegar a un audioprotesista con lenguaje
  diagnóstico no autorizado ("el paciente tiene...") sin que el sistema lo
  bloquee, violando la garantía de seguridad clínica central del producto.
- **Recomendación:** ampliar a un conjunto de patrones/lemas (no solo 3
  strings exactos: variantes verbales, sinónimos, inglés) y/o añadir una
  segunda pasada semántica (LLM-judge dedicado) antes de persistir el
  artefacto, no depender solo del match literal.

---

## B. Alto

### B1. `patients.notes` almacenado en texto plano, sin cifrado de campo
- **Estado (2026-09-23): cerrado.** `notes` migrado a `EncryptedString` (migración `a7c3e59f1b02`, con guardarraíl que aborta si hay datos reales sin backfill; confirmado 0 pacientes con `notes` en staging/producción antes de aplicar). Pusheado a `main` el 2026-09-23 — se aplica sola en el deploy vía `alembic upgrade head`.
- **Dónde:** `backend/app/patients/infrastructure/orm.py:43` —
  `notes: Mapped[str | None] = mapped_column(String(2000), nullable=True)`.
  A diferencia de `display_name`/`birth_year` (líneas 37-38), que sí usan
  `EncryptedString`/`EncryptedInt` (AES-256-GCM, claves versionadas,
  verificado como cifrado real, no solo config presente).
- **Cómo reproducirlo:** cualquier `PATCH /api/v1/patients/{id}` con `notes`
  guarda el valor en claro en la columna.
- **Impacto real:** `notes` es texto libre asociado a un paciente que puede
  contener contenido clínico o sensible, legible directamente en un volcado
  de la base de datos — inconsistente con el resto del modelo de paciente,
  que sí está cifrado en reposo.
- **Recomendación:** migrar `notes` a `EncryptedString`, igual criterio que
  `display_name`.

---

## C. Medio

### C1. Sin borrado/anonimización real de la identidad del paciente (RGPD Art. 17)
- **Estado (2026-09-23): cerrado.** Se decidió **no** separarlo del purge clínico: `purge_patient_clinical_data()` anonimiza ahora in-place la identidad en la misma transacción (`display_name`/`internal_code` a marcadores, `birth_year`/`notes` a `NULL`, nueva columna `identity_purged_at`, migración `b58d1a4f0c93`), también sin sesiones previas. De paso se corrigió `consents.clinical_session_id` a `ondelete="SET NULL"` (sin ello la purga revertía en silencio si había consentimientos ligados). Límite que sigue abierto: backups ya tomados y subencargados (Anthropic no ofrece borrado ad hoc en API de pago) — ver `docs/eipd-dpia.md` §1.7 y §2.2.
- **Dónde:** `backend/app/patients/service.py` — solo existe `archive()`
  (línea 206), que marca `is_archived=True` sin tocar
  `display_name`/`birth_year`/`notes`. `retention/service.py::purge_patient_clinical_data`
  (línea 140) purga físicamente sesiones clínicas, artefactos de IA, audio y
  runs de pipeline — pero la fila de `patients` (identidad cifrada) queda
  intacta indefinidamente.
- **Impacto real:** ante una solicitud de "derecho al olvido" sobre la
  identidad del paciente en sí (no solo el contenido clínico), no hay ningún
  camino en el código para ejecutarla.
- **Recomendación:** añadir un método de anonimización/erasure de
  `patients` (null/hash de los 3 campos + `is_archived=True`), separado del
  purge clínico ya existente.

### C2. Falta cabecera `Content-Security-Policy`
- **Estado (2026-09-23): cerrado.** CSP en backend (`security_headers.py`), nginx de producción y servidor de desarrollo de Vite, verificada contra violaciones reales en la consola del navegador (no solo presencia de cabecera), incluidas las de `/redoc` y el preámbulo de React Fast Refresh.
- **Dónde:** `backend/app/core/security_headers.py` (`SecurityHeadersMiddleware.dispatch`)
  — aplica `X-Content-Type-Options`, `X-Frame-Options: DENY`,
  `Referrer-Policy` y `Strict-Transport-Security` (condicional a producción),
  pero ninguna CSP. Confirmado en vivo con `curl -D-` contra `/health`.
- **Impacto real:** bajo mientras el backend sea API JSON pura, pero
  `/docs`/`/redoc` (Swagger UI, HTML real) están activos en
  desarrollo/staging (`_docs_kwargs_for` solo los desactiva en `production`)
  sin CSP que mitigue una eventual inyección en esa superficie HTML.
- **Recomendación:** añadir `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`
  (o política equivalente) en el mismo middleware.

### C3. `@vitest/mocker` sigue vulnerable tras el bump de esta sesión — el fix real exige `vitest@5.x`
- **Estado (2026-09-23): cerrado.** `vitest` 3.2.7→5.0.1 (sin cambios de configuración; `npm audit`: 0 vulnerabilidades; 285/285 tests de frontend en verde).
- **Dónde:** `frontend/package-lock.json`, confirmado con `npm audit` tras el
  bump de dependencias de hoy (`vitest` 2.1.9→3.2.7).
- **Detalle:** GHSA-82fw-gwwq-j7x9 (path traversal / lectura arbitraria vía
  "Redirect Mock"), rango afectado 2.1.0–4.1.10 — **3.2.7 sigue dentro del
  rango vulnerable**. `npm audit` solo ofrece el fix vía `vitest@5.0.1`
  (`npm audit fix --force`, breaking change).
- **Impacto real:** dependencia de test (Vitest UI server), no llega al
  bundle de producción — riesgo limitado a entornos de desarrollo/CI.
- **Recomendación:** aparte, con el mismo proceso de diff-antes-de-guardar
  que el resto de esta sesión: evaluar el salto a `vitest@5.x` (otro major).
  No se ha tocado en este cierre.

---

## D. Bajo

### D1. JWT sin logout/blacklist explícito — mitigado por chequeo de `is_active` por request
- **Estado (2026-09-24): cerrado.** Contador `token_version` en `users` y `platform_operators` (migración `c91e4d7a2b60`), enviado como claim `tv` del JWT, en lugar del `token_valid_after` contra `iat` recomendado abajo: evita el caso límite de un token emitido en el mismo segundo que el logout o el reset de contraseña (`iat` tiene resolución de segundos). `POST /api/v1/auth/logout` y `POST /api/v1/platform/auth/logout` (204, 5/minute) lo incrementan y cierran todas las sesiones del usuario; también el reset de contraseña (`OnboardingService.confirm_password_reset` y `app.platform_admin.cli reset-password`), en la misma transacción. Un `tv` que no coincide responde el mismo 401 que un token expirado; un token sin `tv` (emitido antes del deploy) cuenta como `tv=0`. El frontend (`signOut` de `AuthContext`/`PlatformAuthContext`) llama al endpoint antes de limpiar el token local y lo limpia igual si falla. Tests: `backend/tests/test_token_revocation.py`. Sigue sin cubrir, fuera de alcance: la filtración de `JWT_SECRET_KEY` (exige rotarla).
- **Dónde:** `backend/app/auth/service.py:22` (TTL 8h clínica),
  `backend/app/platform_admin/service.py:40` (TTL 2h operador), verificación
  en `backend/app/core/current_user.py:105-133`.
- **Detalle:** no hay endpoint de logout ni blacklist — JWT HS256 puro
  stateless. Pero `RealCurrentUserProvider.get_current_user` consulta
  `get_active_by_id` en cada request: si un admin desactiva a un usuario, su
  JWT deja de servir en la siguiente petición aunque no haya expirado. Cubre
  el caso principal (empleado despedido, cuenta comprometida detectada).
- **Lo que queda sin cubrir:** un usuario no puede auto-revocar su propio
  token robado sin intervención de un admin; y todos los tokens (clínica +
  plataforma comparten secreto) quedan comprometidos si `JWT_SECRET_KEY` se
  filtra, hasta rotarlo.
- **Recomendación:** aceptable para el volumen actual. Si se quiere cerrar
  del todo: campo `token_valid_after` por usuario comparado contra `iat` del
  JWT, para permitir auto-logout.

---

## E. Informativo / riesgo ya aceptado y documentado

### E1. Rate limiter en memoria de proceso, no compartido entre réplicas
- `backend/app/core/rate_limit.py:3-17` — límite de `120/minute` general y
  `5/minute` en login (`auth/api/router.py:24`,
  `platform_admin/api/router.py:48`) correctamente aplicados, pero en
  memoria del propio proceso. Con >1 réplica de backend en Railway, el
  límite es por réplica, no global. **Ya documentado como limitación
  conocida y aceptada** en `docs/privacy-and-security.md` mientras el
  despliegue sea de una sola réplica — no es un hallazgo nuevo, se confirma
  aquí que sigue vigente.

### E2. Separación staging/production — documentada y estructuralmente consistente
- `JWT_SECRET_KEY`, `DEEPGRAM_API_KEY`, `RETENTION_CRON_SECRET`,
  `ONBOARDING_CLEANUP_CRON_SECRET`: documentados como valores distintos entre
  staging y production, con `_validate_production_safety` rechazando el
  placeholder de `.env.example` en ambos entornos. No se han leído ni pueden
  leerse los valores reales (política del proyecto) — verificado solo a
  nivel estructural (nombres de variable en `.railway/railway.ts`) y
  documental.

---

## F. Revisado — sin hallazgo (verificado activamente, no solo por lectura)

- **Aislamiento multi-clínica (la garantía más crítica del SaaS):**
  probado en vivo creando una clínica/admin ficticios y accediendo a datos
  de otra clínica (`GET`/`PATCH` paciente ajeno → 404 en los tres intentos;
  listado → vacío). Verificado también por código: **todos** los call-sites
  de `get_by_id(` en `patients`, `clinical_sessions`, `consents`, `billing`,
  `export`, `retention`, `ai_pipeline` reciben `clinic_id` del usuario
  autenticado, nunca de la URL/payload — incluye explícitamente las rutas de
  exportación/PDF. Caso límite en `clinical_sessions/service.py:540`
  (`get_by_id` de `UserRepository` sin filtro de clínica) cerrado
  correctamente por una comprobación explícita en la línea siguiente.
- **Separación de tokens clínica vs. plataforma:** imposible por
  construcción (claim `typ` obligatorio), probado en vivo (`X-Dev-User-Id`
  de clínica → `401` contra endpoints de plataforma).
- **Panel de operador de plataforma:** ve todas las clínicas por diseño
  (correcto, es su función); no hay bug de un admin de clínica viendo otras.
- **`negotiated_included_sessions`/plan de clínica:** solo escribible vía
  `PlatformAdminService`, alcanzable únicamente con JWT de operador de
  plataforma. Ningún endpoint de clínica normal expone esos campos.
- **Webhook de Stripe:** verifica firma real (`stripe.Webhook.construct_event`)
  sobre el body crudo antes de parsear — probado en vivo, firma inválida →
  `400` limpio, sin stack trace. Resistente a replay (tabla de eventos
  procesados por `event.id`, no solo tolerancia de timestamp).
- **CORS:** lista cerrada desde `BACKEND_CORS_ORIGINS`, nunca `*` en
  producción (validado en `app/core/config.py`).
- **Inyección SQL/eval/exec/subprocess/deserialización insegura:** cero
  coincidencias en todo `app/` (grep exhaustivo). ORM sin interpolación de
  strings.
- **SSRF:** sin endpoints que acepten una URL de usuario para fetch
  server-side sin allow-list.
- **Fuzzing en vivo** (paciente, sesión clínica, webhook): payloads
  extremos/inválidos → siempre `422`/`400` estructurado, nunca `500` ni
  traza filtrada (`extra="forbid"` en los esquemas Pydantic probados).
- **Cifrado en reposo real** (no solo config presente): `display_name`,
  `birth_year` de `patients` y `content` de `ai_artifact_versions` usan
  AES-256-GCM con claves versionadas, correctamente wireado en los tipos
  ORM.
- **Logs sin PHI:** los únicos `logger.*` de `ai_pipeline` solo incluyen
  metadatos (`artifact_type`, `provider_name`, `failure_reason`) — nunca
  texto de transcripción. `patients`/`clinical_sessions` no loguean nada.
- **Purga clínica atómica y auditada:** orden correcto de FKs, deja rastro
  en `audit_log`.
- **Inyección de prompt vía transcripción:** separación system/user
  correcta en ambos proveedores LLM reales (Anthropic: campo `system` de
  nivel superior; OpenAI: rol `developer`) — el texto de transcripción
  nunca se concatena dentro del propio `system_prompt`.
- **`GroundingValidator` no evadible por parafraseo:** exige coincidencia
  literal/normalizada como substring real del transcript, no fuzzy/semántico.
- **Fallo de grounding bloquea la generación COMPLETA**, no solo el
  fragmento — confirmado siguiendo el flujo de control real hasta
  `steps/base.py::_attempt`.
- **Dependencias backend:** `pip-audit` tras el bump de esta sesión → 0
  vulnerabilidades conocidas.

---

## Resumen para decisión de negocio

| Categoría | Nº hallazgos | ¿Bloquea alta de primer cliente? |
|---|---|---|
| A — Bloqueante | 1 | **Sí** — `SafetyValidator` evadible |
| B — Alto | 1 | Recomendado antes de datos reales en `notes` |
| C — Medio | 3 | Recomendado, no bloqueante por sí solo |
| D — Bajo | 1 | Aceptable tal cual |
| E — Informativo | 2 | Riesgo ya conocido y documentado |
| F — Sin hallazgo | 16 verificaciones | — |

**El único bloqueante real de este red team es A1** (`SafetyValidator`).
Todo lo demás es mejora recomendada o riesgo ya gestionado. La garantía más
importante del producto — aislamiento multi-clínica — está sólidamente
verificada, incluyendo prueba activa de IDOR, no solo lectura de código.

Ningún fix se ha aplicado en esta fase. Nada de git tocado (commit/push
pendiente de que lo pidas explícitamente).

**Actualización 2026-09-23:** cerrados A1 (mitigado, ver su estado), B1,
C1, C2 y C3. **Actualización 2026-09-24:** cerrado D1 — no queda ningún
hallazgo abierto.
Detalle en la línea de **Estado** de cada hallazgo.
