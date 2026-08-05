# Especificación de API — Audiology AI Assistant (MVP)

API REST bajo `/api/v1`. Autenticación mediante JWT (Bearer). Todas las
rutas salvo `/auth/login` requieren usuario autenticado; las marcadas
`admin` requieren rol `admin`. Respuestas de error siguen el formato
estándar de FastAPI (`{"detail": ...}`).

Esta especificación es de alto nivel (contratos y propósito). El detalle
fino de esquemas Pydantic se define en el código durante la implementación
de cada módulo, siguiendo esta forma.

## Auth / Users

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/auth/login` | público | Devuelve JWT dado email + contraseña |
| GET | `/auth/me` | autenticado | Datos del usuario actual |
| GET | `/users` | admin | Lista usuarios |
| POST | `/users` | admin | Crea usuario |
| PATCH | `/users/{user_id}` | admin | Activa/desactiva, cambia rol |

## Patients

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/patients` | clinician/admin | Lista pacientes (filtrable por nombre/referencia) |
| POST | `/patients` | clinician/admin | Crea paciente ficticio (`is_fictional` forzado a `true`) |
| GET | `/patients/{patient_id}` | clinician/admin | Detalle de identidad del paciente |
| PATCH | `/patients/{patient_id}` | clinician/admin | Edita datos identificativos |

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
