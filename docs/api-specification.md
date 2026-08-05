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
apoyo `/me`, `/dev/users`) están implementadas, desde la Fase 2. La
sección **Clinical sessions** está **diseñada y cerrada** en la Fase 3,
pendiente de implementación. El resto de secciones de este documento
describen el diseño objetivo de fases futuras y no tienen código todavía
(ver [development-plan.md](development-plan.md)).

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

Diseño cerrado en la Fase 3, backend en implementación. Reemplaza el
diseño anterior basado en `ProcessingStatus` y rutas anidadas bajo
`/patients/{id}/sessions` — ver nota de corrección en
[data-model.md](data-model.md) §6.

Todas las rutas van bajo `/clinical-sessions` (no anidadas bajo
`/patients`, a diferencia del diseño previo) y requieren un `CurrentUser`
resuelto, operando exclusivamente sobre `current_user.clinic_id`.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/clinical-sessions` | Crea una sesión; `status` inicial elegido entre `scheduled`, `in_progress`, `completed` |
| GET | `/clinical-sessions` | Lista paginada, con filtros (ver Listado) |
| GET | `/clinical-sessions/{session_id}` | Detalle; `404` si no existe o pertenece a otra clínica |
| PATCH | `/clinical-sessions/{session_id}` | Actualización parcial de metadatos y, si autorizado, `professional_id`; `409` si no editable en el estado actual |
| POST | `/clinical-sessions/{session_id}/start` | `scheduled → in_progress` (no-op si ya `in_progress`) |
| POST | `/clinical-sessions/{session_id}/complete` | `in_progress → completed` (no-op si ya `completed`) |
| POST | `/clinical-sessions/{session_id}/submit-review` | `completed → review_pending` (no-op si ya `review_pending`) |
| POST | `/clinical-sessions/{session_id}/review` | `review_pending → reviewed` (no-op si ya `reviewed`); solo `admin` |
| POST | `/clinical-sessions/{session_id}/cancel` | `{scheduled,in_progress} → cancelled` (no-op si ya `cancelled`) |
| POST | `/clinical-sessions/{session_id}/archive` | Archiva (idempotente); solo desde `completed`, `reviewed` o `cancelled` — nunca desde `review_pending` |
| POST | `/clinical-sessions/{session_id}/restore` | Restaura (idempotente); solo `admin` |

No existe un endpoint genérico de cambio de estado
(`PATCH .../status`): se prioriza claridad, trazabilidad y permisos
explícitos por acción — ver decisión en
[architecture.md](architecture.md) §11. Tampoco existe `DELETE`: el
borrado físico no se implementa, igual que en `patients`.

### Máquina de estados (resumen)

```
creación → scheduled | in_progress | completed
scheduled      --start-->          in_progress
scheduled      --cancel-->         cancelled
in_progress    --complete-->       completed
in_progress    --cancel-->         cancelled
completed      --submit-review-->  review_pending
review_pending --review-->         reviewed
```

`reviewed` y `cancelled` son terminales para `status` (solo admiten
archivar). Detalle completo de transiciones, idempotencia y efectos sobre
fechas en [data-model.md](data-model.md) §8.

### Autorización (matriz de permisos)

Centralizada en `core/authorization.py`
(`authorize_clinical_session_action`, ver
[architecture.md](architecture.md) §9), con una dimensión adicional de
**propiedad** respecto a `patients`: para `audiologist`, "sus propias
sesiones" significa `professional_id == current_user.id`.

| Acción | admin | audiologist | viewer |
|---|:---:|:---:|:---:|
| Crear (`POST`) | ✅ (cualquier profesional admin/audiologist de la clínica) | ✅ (solo con `professional_id = sí mismo`) | ❌ |
| Leer (`GET` lista/detalle) | ✅ | ✅ (sin restricción de propiedad) | ✅ |
| Actualizar metadatos (`PATCH` sin `professional_id`) | ✅ (`review_pending` limita a `title`/`administrative_notes`, ver [data-model.md](data-model.md) §8) | ✅ (solo sesiones propias; misma limitación en `review_pending`) | ❌ |
| Cambiar profesional (`PATCH` con `professional_id`) | ✅ (nunca en `review_pending`) | ❌ | ❌ |
| Iniciar (`.../start`) | ✅ | ✅ (solo propias) | ❌ |
| Completar (`.../complete`) | ✅ | ✅ (solo propias) | ❌ |
| Enviar a revisión (`.../submit-review`) | ✅ | ✅ (solo propias) | ❌ |
| Revisar (`.../review`) | ✅ | ❌ | ❌ |
| Cancelar (`.../cancel`) | ✅ | ✅ (solo propias, y solo desde `scheduled`/`in_progress`) | ❌ |
| Archivar (`.../archive`) | ✅ | ✅ (solo propias, y solo desde `completed`/`reviewed`/`cancelled` — nunca `review_pending`) | ❌ |
| Restaurar (`.../restore`) | ✅ | ❌ | ❌ |

Decisiones no fijadas explícitamente por el encargo y resueltas aquí de
la forma más simple y segura para el MVP (ver justificación en
[product-requirements.md](product-requirements.md) §11):

- **Un `audiologist` no puede editar, iniciar, completar, enviar a
  revisión, cancelar ni archivar sesiones de otros profesionales de su
  misma clínica** — solo las suyas. Evita que un profesional modifique el
  registro clínico de un compañero sin su intervención.
- **`review` es exclusivo de `admin`.** Con solo tres roles y sin una
  noción de "profesional senior" o revisor por pares, permitir que un
  `audiologist` revisara sus propias sesiones habría vaciado de sentido
  el paso de revisión (autorrevisión). Si se necesita revisión entre
  pares en el futuro, requiere un rol o regla nueva, fuera de esta fase.
- **Un `audiologist` que crea una sesión solo puede asignarse a sí mismo
  como `professional_id`.** Evita que cree registros nominalmente
  responsabilidad de un compañero sin su participación. `admin` puede
  asignar a cualquier `admin`/`audiologist` de la clínica.

Un intento sin permiso devuelve `403`. Un `session_id` válido de otra
clínica devuelve `404`, nunca `403` (igual que `patients`, ver
[architecture.md](architecture.md) §10).

### Listado (`GET /clinical-sessions`)

Parámetros de query:

| Parámetro | Tipo | Default | Notas |
|---|---|---|---|
| `patient_id` | UUID, opcional | — | Sesiones de un paciente (usado también en la vista de detalle de paciente) |
| `professional_id` | UUID, opcional | — | Filtro por profesional responsable |
| `status` | string, opcional | — | Uno de `ClinicalSessionStatus` |
| `session_type` | string, opcional | — | Uno de los tipos fijos (ver Validaciones) |
| `scheduled_from` / `scheduled_to` | date, opcional | — | Rango sobre `scheduled_at` exclusivamente (ver limitación en [data-model.md](data-model.md) §9); nombres de parámetro cerrados, no `date_from`/`date_to` |
| `search` | string, opcional | — | Coincidencia parcial (case-insensitive) contra `title` o `administrative_notes` |
| `include_archived` | bool | `false` | Si es `false`, excluye sesiones con `is_archived = true` |
| `limit` | int | `20` | Máximo `PAGINATION_MAX_LIMIT`; `422` si se supera |
| `offset` | int | `0` | |

Orden estable: `created_at ASC, id ASC` (igual que `patients`, ver
[data-model.md](data-model.md) §9 sobre por qué el orden no usa
`scheduled_at`). Respuesta: `{"items": [...], "total": N, "limit": L,
"offset": O}`.

### Validaciones (`POST` / `PATCH`)

- `patient_id` (solo `POST`, inmutable después): obligatorio; `404` si no
  existe en la clínica; `409` si el paciente está archivado.
- `professional_id`: obligatorio en creación; `404` si el usuario no
  existe en la clínica; `409` si existe pero está inactivo, o si su rol
  no es `admin`/`audiologist` (un `viewer` nunca puede ser profesional
  responsable).
- `session_type`: obligatorio, uno de `initial_assessment`, `follow_up`,
  `hearing_aid_fitting`, `hearing_aid_adjustment`, `review`, `other`.
- `status` (solo `POST`): opcional, default `scheduled`; si se informa,
  debe ser uno de `scheduled`, `in_progress`, `completed` — cualquier
  otro valor (`review_pending`, `reviewed`, `cancelled`) se rechaza con
  `422`, ya que solo se alcanzan mediante los endpoints de transición.
- `scheduled_at`: datetime ISO 8601 opcional; puede ser futura. Único
  campo de fecha que acepta el cliente.
- `started_at`, `ended_at`, `reviewed_by`, `reviewed_at`: **no existen en
  ningún esquema de entrada** (ni `POST` ni `PATCH`); enviarlos se
  rechaza con `422` como cualquier otro campo no reconocido. Los fija
  siempre el servidor — ver [data-model.md](data-model.md) §8.
- `title`: opcional, hasta 200 caracteres, espacios normalizados.
- `administrative_notes`: opcional, hasta 2000 caracteres, espacios
  normalizados, exclusivamente administrativas.
- Campos no reconocidos (incluidos `clinic_id`, `status`, `started_at`,
  `ended_at`, `reviewed_by`, `reviewed_at`, `created_by`, `created_at`,
  `updated_at`, `id`, `schema_version` en `PATCH`) se **rechazan con
  `422`** — no existen en los esquemas de entrada correspondientes.
- `PATCH` sobre una sesión no editable en su estado actual (`reviewed`,
  `cancelled`) o archivada devuelve `409`. En `review_pending`, `PATCH`
  con cualquier campo distinto de `title`/`administrative_notes`
  (incluido `professional_id`) también devuelve `409`.
- Las transiciones (`start`/`complete`/`submit-review`/`review`/`cancel`)
  devuelven `409` si el estado actual no admite esa transición ni es ya
  el estado de destino (ver tabla de idempotencia en
  [data-model.md](data-model.md) §8).
- `archive` devuelve `409` si `status ∉ {completed, reviewed,
  cancelled}` — explícitamente incluye `review_pending` como estado que
  **no** admite archivado.

## Audio

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/clinical-sessions/{session_id}/audio` | clinician | Sube fichero de audio (multipart); crea `audio_recordings` en `uploaded`, dispara validación (tamaño/duración/extensión/MIME) hacia `validating` → `ready`/`failed` |
| GET | `/clinical-sessions/{session_id}/audio` | clinician/admin | Metadatos del audio (no el binario) |
| GET | `/clinical-sessions/{session_id}/audio/download` | clinician/admin | Descarga del binario vía `AudioStorage`, auditado |
| DELETE | `/clinical-sessions/{session_id}/audio` | clinician/admin | Borrado físico manual vía `RetentionCleanupService` (`status → deleted`, `storage_reference` invalidado); metadatos conservados |

## Transcription

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/clinical-sessions/{session_id}/transcription` | clinician | Dispara transcripción vía `TranscriptionProvider` activo; requiere audio en `ready`; `transcribing` → `transcribed`/`failed` |
| GET | `/clinical-sessions/{session_id}/transcription` | clinician/admin | Obtiene texto transcrito |

## Anamnesis

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/clinical-sessions/{session_id}/anamnesis/generate` | clinician | Genera borrador vía `LanguageModelProvider` a partir de la transcripción; `generating` → `review_pending`/`failed`; fija `schema_version` |
| GET | `/clinical-sessions/{session_id}/anamnesis` | clinician/admin | Documento actual (contenido + `schema_version` + estado + aviso IA) |
| PUT | `/clinical-sessions/{session_id}/anamnesis` | clinician | Guarda `current_content` editado; crea `document_versions`; permanece/vuelve a `review_pending` (si venía de `approved`, exige nueva aprobación) |
| POST | `/clinical-sessions/{session_id}/anamnesis/approve` | clinician | Aprobación explícita; estado → `approved`, registra `approved_by/at` |
| DELETE | `/clinical-sessions/{session_id}/anamnesis` | clinician/admin | Borrado lógico (`status → deleted`, `deleted_by/at`); nunca físico; `document_versions` se conserva |
| GET | `/clinical-sessions/{session_id}/anamnesis/versions` | clinician/admin | Historial de versiones |

## Session notes (resumen profesional)

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| POST | `/clinical-sessions/{session_id}/session-notes/generate` | clinician | Genera resumen vía `LanguageModelProvider`; `generating` → `review_pending`/`failed` |
| GET | `/clinical-sessions/{session_id}/session-notes` | clinician/admin | Resumen actual + estado |
| PUT | `/clinical-sessions/{session_id}/session-notes` | clinician | Guarda edición; nueva versión; misma regla de re-aprobación que anamnesis |
| POST | `/clinical-sessions/{session_id}/session-notes/approve` | clinician | Aprobación explícita |
| DELETE | `/clinical-sessions/{session_id}/session-notes` | clinician/admin | Borrado lógico únicamente, auditado |
| GET | `/clinical-sessions/{session_id}/session-notes/versions` | clinician/admin | Historial de versiones |

## Clinical flags

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/clinical-sessions/{session_id}/clinical-flags` | clinician/admin | Lista de señales sugeridas/confirmadas/descartadas, generadas por el `ClinicalFlagRuleset` activo (`ruleset_name` en cada ítem); respuesta incluye aviso de checklist no validado clínicamente |
| PATCH | `/clinical-flags/{flag_id}` | clinician | Cambia estado (`confirmada_por_profesional` / `descartada`) |

## Export

| Método | Ruta | Rol | Descripción |
|---|---|---|---|
| GET | `/clinical-sessions/{session_id}/export/anamnesis?format=pdf\|text` | clinician/admin | Exporta anamnesis; **solo si `status = approved`** |
| GET | `/clinical-sessions/{session_id}/export/session-notes?format=pdf\|text` | clinician/admin | Exporta resumen; **solo si `status = approved`** |

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
