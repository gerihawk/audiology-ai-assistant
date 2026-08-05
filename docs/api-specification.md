# Especificación de API — Audiology AI Assistant (MVP)

API REST bajo `/api/v1`. **Sin autenticación real todavía** (ver
[architecture.md](architecture.md) §9): la identidad del usuario se
resuelve mediante `CurrentUserProvider`; en el MVP, `FakeCurrentUserProvider`
la obtiene de la cabecera de desarrollo `X-Dev-User-Id` (UUID de un
usuario existente y activo en `users`) o, si no se envía, de
`DEV_DEFAULT_USER_ID`. Esta cabecera **no sustituye** a un mecanismo de
autenticación real y se rechaza (arranque fallido) si
`ENVIRONMENT=production`. Todas las rutas de negocio requieren un
`CurrentUser` resuelto (401 si no); las marcadas con un rol exigen que
`current_user.role` tenga permiso para la acción, según la matriz de
autorización de cada recurso (ver más abajo). El acceso está siempre
acotado a `current_user.clinic_id`; nunca se acepta un `clinic_id` desde
el cliente.

Respuestas de error usan el formato `{"error": {"code": ..., "message":
..., ...}}` (ver [architecture.md](architecture.md), manejo global de
errores).

Esta especificación es de alto nivel (contratos y propósito). El detalle
fino de esquemas Pydantic se define en el código durante la implementación
de cada módulo, siguiendo esta forma.

**Estado de implementación**: solo la sección **Patients** (y sus rutas de
apoyo `/me`, `/dev/users`) están implementadas, desde la Fase 2. El resto
de secciones de este documento describen el diseño objetivo de fases
futuras y no tienen código todavía (ver
[development-plan.md](development-plan.md)).

## Dev tools (solo desarrollo, ausentes en producción)

No forman parte del alcance mínimo pedido para `patients`, pero son
necesarias para poder ejercitar `CurrentUserProvider` desde el frontend
sin autenticación real. Estas rutas **no se registran** cuando
`ENVIRONMENT=production` (no existen, no devuelven 403: menor superficie).

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/dev/users` | público (solo no-producción) | Lista `{id, display_name, role, clinic_id}` de todos los usuarios, para poblar un selector de "usuario activo" en el frontend de desarrollo |
| GET | `/me` | autenticado | Datos del `CurrentUser` resuelto (id, clinic_id, email, display_name, role) |

## Patients

Recurso implementado en la Fase 2. Todas las rutas requieren un
`CurrentUser` resuelto y operan exclusivamente sobre `current_user.clinic_id`.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/patients` | Crea un paciente ficticio en la clínica del usuario actual |
| GET | `/patients` | Lista paginada, con búsqueda y filtro de archivados (ver Listado) |
| GET | `/patients/{patient_id}` | Detalle; `404` si no existe o pertenece a otra clínica |
| PATCH | `/patients/{patient_id}` | Actualización parcial; `409` si el paciente está archivado |
| POST | `/patients/{patient_id}/archive` | Archiva (idempotente); ver Autorización |
| POST | `/patients/{patient_id}/restore` | Restaura (idempotente); ver Autorización |

### Autorización (matriz de permisos)

Centralizada en `core/authorization.py` (ver
[architecture.md](architecture.md) §9); ningún endpoint implementa
comprobaciones de rol propias.

| Acción | admin | audiologist | viewer |
|---|:---:|:---:|:---:|
| Crear (`POST /patients`) | ✅ | ✅ | ❌ |
| Leer (`GET /patients`, `GET /patients/{id}`) | ✅ | ✅ | ✅ |
| Actualizar (`PATCH /patients/{id}`) | ✅ | ✅ | ❌ |
| Archivar (`POST .../archive`) | ✅ | ✅ | ❌ |
| Restaurar (`POST .../restore`) | ✅ | ❌ | ❌ |

`audiologist` puede archivar pero no restaurar — la fase no especifica el
permiso de restauración para este rol de forma explícita, así que se
adopta la regla más conservadora (restaurar queda reservado a `admin`),
documentada aquí como decisión cerrada.

Un intento sin permiso devuelve `403`. Un `patient_id` válido de otra
clínica devuelve `404`, nunca `403` (ver
[architecture.md](architecture.md) §10) — no debe ser posible distinguir
"no tienes permiso" de "no existe" para recursos ajenos a la propia
clínica.

### Listado (`GET /patients`)

Parámetros de query:

| Parámetro | Tipo | Default | Notas |
|---|---|---|---|
| `search` | string, opcional | — | Coincidencia parcial (case-insensitive) contra `internal_code` o `display_name` |
| `include_archived` | bool | `false` | Si es `false`, excluye pacientes con `is_archived = true` |
| `limit` | int | `20` | Máximo `PAGINATION_MAX_LIMIT` (configurable, default 100); `422` si se supera |
| `offset` | int | `0` | |

Orden estable: `created_at ASC, id ASC`. Respuesta:
`{"items": [...], "total": N, "limit": L, "offset": O}`.

### Validaciones (`POST` / `PATCH`)

- `internal_code`: obligatorio en creación, `1-64` caracteres tras
  normalizar (recorte de espacios), patrón `[A-Za-z0-9._-]+`. Conflicto
  (`409`, con `field: "internal_code"`) si ya existe otro paciente con el
  mismo código en la misma clínica.
- `display_name`: opcional, hasta 200 caracteres, espacios internos
  colapsados.
- `birth_year`: opcional, entero entre 1900 y el año actual.
- `sex`: opcional, uno de `female`, `male`, `other`, `unspecified`.
- `preferred_language`: opcional en creación (default `es`); único valor
  aceptado en el MVP es `es`.
- `notes`: opcional, hasta 2000 caracteres, exclusivamente administrativas.
- Cualquier campo no reconocido en el cuerpo (incluidos `clinic_id`,
  `created_by`, `updated_by`, `created_at`, `updated_at`, `id`,
  `schema_version`) se **rechaza con `422`** — estos campos ni siquiera
  existen en los esquemas de entrada, no se filtran en tiempo de
  ejecución.
- `PATCH` sobre un paciente archivado devuelve `409` (debe restaurarse
  primero).

## Clinical sessions

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/patients/{patient_id}/sessions` | clinician/admin | Sesiones de un paciente |
| POST | `/patients/{patient_id}/sessions` | clinician/admin | Crea sesión (estado inicial `created`) |
| GET | `/sessions/{session_id}` | clinician/admin | Detalle de sesión, incluye `status` (`ProcessingStatus`) agregado |
| GET | `/sessions/{session_id}/timeline` | clinician/admin | Eventos de auditoría relevantes de esa sesión |
| DELETE | `/sessions/{session_id}` | clinician/admin | Borrado lógico (`status → deleted`), nunca físico; auditado |

## Audio

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/sessions/{session_id}/audio` | clinician | Sube fichero de audio (multipart); crea `audio_recordings` en `uploaded`, dispara validación (tamaño/duración/extensión/MIME) hacia `validating` → `ready`/`failed` |
| GET | `/sessions/{session_id}/audio` | clinician/admin | Metadatos del audio (no el binario) |
| GET | `/sessions/{session_id}/audio/download` | clinician/admin | Descarga del binario vía `AudioStorage`, auditado |
| DELETE | `/sessions/{session_id}/audio` | clinician/admin | Borrado físico manual vía `RetentionCleanupService` (`status → deleted`, `storage_reference` invalidado); metadatos conservados |

## Transcription

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/sessions/{session_id}/transcription` | clinician | Dispara transcripción vía `TranscriptionProvider` activo; requiere audio en `ready`; `transcribing` → `transcribed`/`failed` |
| GET | `/sessions/{session_id}/transcription` | clinician/admin | Obtiene texto transcrito |

## Anamnesis

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/sessions/{session_id}/anamnesis/generate` | clinician | Genera borrador vía `LanguageModelProvider` a partir de la transcripción; `generating` → `review_pending`/`failed`; fija `schema_version` |
| GET | `/sessions/{session_id}/anamnesis` | clinician/admin | Documento actual (contenido + `schema_version` + estado + aviso IA) |
| PUT | `/sessions/{session_id}/anamnesis` | clinician | Guarda `current_content` editado; crea `document_versions`; permanece/vuelve a `review_pending` (si venía de `approved`, exige nueva aprobación) |
| POST | `/sessions/{session_id}/anamnesis/approve` | clinician | Aprobación explícita; estado → `approved`, registra `approved_by/at` |
| DELETE | `/sessions/{session_id}/anamnesis` | clinician/admin | Borrado lógico (`status → deleted`, `deleted_by/at`); nunca físico; `document_versions` se conserva |
| GET | `/sessions/{session_id}/anamnesis/versions` | clinician/admin | Historial de versiones |

## Session notes (resumen profesional)

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/sessions/{session_id}/session-notes/generate` | clinician | Genera resumen vía `LanguageModelProvider`; `generating` → `review_pending`/`failed` |
| GET | `/sessions/{session_id}/session-notes` | clinician/admin | Resumen actual + estado |
| PUT | `/sessions/{session_id}/session-notes` | clinician | Guarda edición; nueva versión; misma regla de re-aprobación que anamnesis |
| POST | `/sessions/{session_id}/session-notes/approve` | clinician | Aprobación explícita |
| DELETE | `/sessions/{session_id}/session-notes` | clinician/admin | Borrado lógico únicamente, auditado |
| GET | `/sessions/{session_id}/session-notes/versions` | clinician/admin | Historial de versiones |

## Clinical flags

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/sessions/{session_id}/clinical-flags` | clinician/admin | Lista de señales sugeridas/confirmadas/descartadas, generadas por el `ClinicalFlagRuleset` activo (`ruleset_name` en cada ítem); respuesta incluye aviso de checklist no validado clínicamente |
| PATCH | `/clinical-flags/{flag_id}` | clinician | Cambia estado (`confirmada_por_profesional` / `descartada`) |

## Export

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/sessions/{session_id}/export/anamnesis?format=pdf\|text` | clinician/admin | Exporta anamnesis; **solo si `status = approved`** |
| GET | `/sessions/{session_id}/export/session-notes?format=pdf\|text` | clinician/admin | Exporta resumen; **solo si `status = approved`** |

## Consents

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/patients/{patient_id}/consents` | clinician/admin | Lista consentimientos registrados |
| POST | `/patients/{patient_id}/consents` | clinician | Registra un consentimiento (tipo, otorgado sí/no) |

## Audit log

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/audit-log` | admin | Consulta paginada, filtrable por entidad/usuario/rango de fechas |

## Integrations (configuración, no ejecución real)

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/integrations` | admin | Estado de cada integración abstracta (proveedor activo, habilitada) |
| PATCH | `/integrations/{integration_name}` | admin | Cambia proveedor activo (en el MVP, solo valores `mock`) |

## Retention (limpieza manual)

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/retention/expired-audio` | admin | Lista audios que superan `RETENTION_DAYS_DEFAULT` vía `RetentionCleanupService.find_expired_audio` |
| POST | `/retention/expired-audio/purge` | admin | Ejecuta el borrado físico manual de los audios listados; no hay scheduler en el MVP |

## Convenciones transversales

- Toda respuesta que incluya contenido generado por IA (anamnesis,
  resumen, clinical flags antes de confirmación) incluye un campo
  `ai_disclaimer` con el texto obligatorio definido en
  [clinical-safety.md](clinical-safety.md). Las respuestas de
  `clinical-flags` incluyen además `ruleset_disclaimer` (checklist de
  demostración, no validado clínicamente).
- Las rutas de exportación devuelven `409 Conflict` si el documento no
  está `approved`.
- Las rutas de escritura sobre pacientes/sesiones/documentos registran una
  entrada en `audit_log` de forma síncrona antes de responder `2xx`,
  incluidos fallos (`status = failed`) y borrados.
- Cualquier transición de estado inválida (p. ej. aprobar sin generar,
  transcribir sin audio `ready`) devuelve `409 Conflict` con el motivo;
  la validación ocurre en la capa de dominio/servicio, no solo en el
  router (ver [architecture.md](architecture.md) §5).
- Las respuestas de audio y sesión nunca incluyen `storage_reference` en
  bruto al frontend; solo se usa internamente para resolver
  `/audio/download`.
