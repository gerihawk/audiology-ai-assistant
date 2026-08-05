# Modelo de datos — Audiology AI Assistant

## 1. Principio rector: identidad vs. contenido clínico

`patients` almacena únicamente la **identidad mínima** necesaria para
distinguir a un paciente ficticio (nombre, fecha de nacimiento, referencia
interna). Ningún otro módulo duplica estos campos: todos referencian
`patient_id`. Esto permite en el futuro aplicar controles de acceso,
cifrado o retención distintos a la identidad frente al contenido clínico
sin rediseñar el esquema.

Todos los identificadores públicos (los expuestos por la API) son **UUID**;
no se exponen identificadores secuenciales en ninguna entidad.

## 2. Entidades

### `clinics`
El sistema es **multi-clínica desde el modelo de datos**, aunque durante el
MVP exista una única clínica de desarrollo (creada por seed, ver
[development-plan.md](development-plan.md) Fase 2). Toda entidad con datos
de clínica referencia `clinic_id`; ninguna consulta de listado o detalle
puede omitir ese filtro (ver `architecture.md` §9 sobre aislamiento por
clínica).

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| name | string(200) | |
| code | string(32), único globalmente | Identificador corto legible, p. ej. `DEV-CLINIC` |
| is_active | bool, default true | |
| created_at / updated_at | timestamp | |

### `users`
Sin autenticación real en el MVP (ver §7 y
[architecture.md](architecture.md) §10 `CurrentUserProvider`). El email es
único **globalmente** (no solo por clínica): sirve de identificador de
login incluso antes de que exista un mecanismo de autenticación real, y
simplifica la resolución del usuario ficticio de desarrollo.

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| clinic_id | FK clinics.id | |
| email | string(254), único globalmente | |
| display_name | string(200) | |
| role | enum | `admin`, `audiologist`, `viewer` — ver matriz de permisos en [api-specification.md](api-specification.md) §Autorización |
| is_active | bool, default true | Un usuario inactivo nunca puede resolverse como `CurrentUser` |
| created_at / updated_at | timestamp | |

Sin campo de contraseña ni tokens: fuera de alcance hasta que exista
autenticación real (fase futura, no planificada todavía).

### `patients`
Identidad y datos administrativos mínimos del paciente **ficticio**. Sin
ningún campo clínico (motivo de consulta, diagnóstico, audiometrías,
anamnesis, contenido de sesión) ni dato personal sensible más allá de lo
estrictamente necesario para distinguirlo en la UI — nunca DNI, número de
seguridad social, dirección, teléfono ni email personal. El contenido
clínico (`clinical_sessions` y módulos posteriores) referenciará
`patient_id` sin duplicar estos campos, preservando la separación
identidad/clínica de §1.

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | Identificador público |
| clinic_id | FK clinics.id | |
| internal_code | string(64) | Normalizado (recortado, sin espacios internos), patrón `[A-Za-z0-9._-]+`. **Único por clínica**: `UNIQUE (clinic_id, internal_code)` — no globalmente único |
| display_name | string(200), nullable | Opcional; espacios normalizados |
| birth_year | int, nullable | Rango razonable: 1900–año actual |
| sex | enum, nullable | `female`, `male`, `other`, `unspecified` — administrativo, no clínico |
| preferred_language | string(5), default `es` | Único valor soportado en el MVP (`es`), preparado para más adelante (ver `architecture.md` §8) |
| notes | string(2000), nullable | Exclusivamente notas administrativas ficticias; nunca contenido clínico |
| is_archived | bool, default false | Ver §7 Archivado |
| created_by | FK users.id | |
| updated_by | FK users.id | |
| created_at / updated_at | timestamp | `updated_at` con `onupdate` a nivel de base de datos |
| archived_at | timestamp, nullable | |
| schema_version | int, default 1 | Versión del esquema fijo de campos de `patients`, análogo a `anamnesis_documents.schema_version` |

Índice único: `UNIQUE (clinic_id, internal_code)`. Índices adicionales en
§7 (búsqueda por clínica, estado archivado, fechas).

### `clinical_sessions`
Entidad central sobre la que, en fases futuras, se asociarán audio,
transcripción, anamnesis, notas de sesión, señales clínicas, documentos,
tareas e integraciones — ninguna de ellas implementada todavía. Sin
contenido clínico real: `administrative_notes` es estrictamente
administrativo, igual que `patients.notes`. Diseño cerrado en la Fase 3
(ver [development-plan.md](development-plan.md) Fase 3); implementación
de backend en curso.

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | Identificador público |
| clinic_id | FK clinics.id | Nunca editable tras la creación |
| patient_id | FK patients.id | Nunca editable tras la creación; el paciente no puede estar archivado en el momento de crear la sesión |
| professional_id | FK users.id | Profesional responsable único (sin edición colaborativa); debe pertenecer a la misma clínica, estar activo y tener rol `admin` o `audiologist` — nunca `viewer` |
| session_type | string(32) | `initial_assessment`, `follow_up`, `hearing_aid_fitting`, `hearing_aid_adjustment`, `review`, `other` — conjunto fijo, no configurable por clínica en el MVP |
| status | enum (`ClinicalSessionStatus`) | `scheduled`, `in_progress`, `completed`, `review_pending`, `reviewed`, `cancelled` — máquina de estados propia, **no** `ProcessingStatus` (ver §8) |
| scheduled_at | timestamp, nullable | Fecha/hora prevista; puede ser futura; único campo de fecha que acepta el cliente |
| started_at | timestamp, nullable | Fijado **exclusivamente por el servidor**; nunca aceptado del cliente (ni en creación ni en edición) — ver §8 |
| ended_at | timestamp, nullable | Fijado **exclusivamente por el servidor**; nunca aceptado del cliente; `≥ started_at` |
| title | string(200), nullable | Espacios normalizados; editable en `review_pending` |
| administrative_notes | string(2000), nullable | Exclusivamente administrativas; nunca contenido clínico real; editable en `review_pending` |
| reviewed_by | FK users.id, nullable | Fijado **exclusivamente por el servidor** al ejecutar `.../review` (actor); nunca aceptado del cliente |
| reviewed_at | timestamp, nullable | Fijado **exclusivamente por el servidor** al ejecutar `.../review`; nunca aceptado del cliente |
| created_by | FK users.id | |
| updated_by | FK users.id | |
| created_at / updated_at | timestamp | `updated_at` con `onupdate` a nivel de base de datos |
| schema_version | int, default 1 | Mismo patrón que `patients.schema_version` |
| is_archived | bool, default false | Eje independiente de `status` — ver §8 |
| archived_at | timestamp, nullable | |

`reviewed_by`/`reviewed_at` son columnas propias (decisión cerrada tras
revisar el diseño inicial de la Fase 3, que proponía derivarlas solo de
`audit_logs`): permiten mostrar "revisado por/cuándo" sin unir contra la
auditoría, que en todo caso sigue conservando el historial completo de
cada transición. Ver [product-requirements.md](product-requirements.md)
§11.

### `audio_recordings`
Solo metadatos: el binario nunca se almacena en PostgreSQL.

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| clinical_session_id | FK clinical_sessions.id | |
| status | enum (`ProcessingStatus`) | `uploaded`, `validating`, `ready`, `transcribing`, `transcribed`, `failed`, `deleted` |
| storage_provider | string | p. ej. `local` (nombre del `AudioStorage` activo) |
| storage_reference | string, nullable | Referencia opaca devuelta por `AudioStorage`; se invalida (`null`) tras borrado físico |
| original_filename | string | |
| mime_type | string | Validado contra lista blanca configurable |
| extension | string | Validado contra lista blanca configurable |
| duration_seconds | int, nullable | Se completa tras validación; obligatorio para pasar a `ready` |
| size_bytes | int | Validado contra `AUDIO_MAX_SIZE_MB` |
| checksum | string | Integridad del fichero (hash) |
| failure_reason | text, nullable | Motivo si `status = failed` |
| uploaded_by | FK users.id | |
| uploaded_at | timestamp | |
| deleted_at | timestamp, nullable | Fecha de borrado físico (retención) |

### `transcriptions`
| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| audio_recording_id | FK audio_recordings.id, único | 1:1 con el audio; la fila solo existe si la transcripción se completó (el estado del proceso vive en `audio_recordings.status`) |
| provider_name | string | p. ej. `mock` |
| raw_text | text | Transcripción completa |
| language | string | p. ej. `es` |
| created_at | timestamp | |

### `anamnesis_documents`
Documento estructurado por campos. Ver §3 para el listado de campos.

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| clinical_session_id | FK clinical_sessions.id, único | 1:1 con la sesión |
| schema_version | int, default 1 | Versión del esquema fijo de campos de anamnesis (§3); permite evolucionar el esquema sin migrar documentos existentes |
| ai_generated_content | JSONB | Salida original del `LanguageModelProvider`, inmutable |
| current_content | JSONB | Contenido editable actual (campo por campo, ver §3) |
| status | enum (`ProcessingStatus`) | `generating`, `review_pending`, `approved`, `failed`, `deleted` |
| approved_by | FK users.id, nullable | |
| approved_at | timestamp, nullable | |
| deleted_at | timestamp, nullable | Borrado **lógico únicamente**; un documento `approved` nunca se elimina físicamente |
| deleted_by | FK users.id, nullable | |
| created_at / updated_at | timestamp | |

### `session_notes`
Resumen profesional de la sesión. Mismo patrón que `anamnesis_documents`.

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| clinical_session_id | FK clinical_sessions.id, único | |
| schema_version | int, default 1 | |
| ai_generated_content | text | Resumen original generado por IA |
| current_content | text | Resumen editable actual |
| status | enum (`ProcessingStatus`) | `generating`, `review_pending`, `approved`, `failed`, `deleted` |
| approved_by | FK users.id, nullable | |
| approved_at | timestamp, nullable | |
| deleted_at | timestamp, nullable | Borrado lógico únicamente |
| deleted_by | FK users.id, nullable | |
| created_at / updated_at | timestamp | |

### `document_versions`
Historial de cambios, común a `anamnesis_documents` y `session_notes`
(tabla única con discriminador de tipo, dado que ambos comparten el mismo
ciclo de vida de edición/aprobación).

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| document_type | enum | `anamnesis`, `session_note` |
| document_id | UUID | Referencia lógica a `anamnesis_documents.id` o `session_notes.id` según `document_type` |
| content | JSONB o text | Snapshot del contenido en ese momento |
| edited_by | FK users.id | |
| edited_at | timestamp | |
| change_note | text, nullable | Comentario opcional del profesional |

### `clinical_flags`
| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| clinical_session_id | FK clinical_sessions.id | |
| category | string | p. ej. `otalgia`, `perdida_asimetrica`, `tinnitus_unilateral` |
| description | text | Redactado en lenguaje no diagnóstico (ver clinical-safety.md) |
| source_excerpt | text, nullable | Fragmento de la transcripción que originó la señal |
| ruleset_name | string | p. ej. `demo_generic_v1`; identifica qué `ClinicalFlagRuleset` la generó, para trazabilidad si se sustituye por un protocolo validado |
| status | enum | `sugerida_ia`, `confirmada_por_profesional`, `descartada` — eje de disposición del profesional, independiente de `ProcessingStatus` (ver architecture.md §5) |
| reviewed_by | FK users.id, nullable | |
| reviewed_at | timestamp, nullable | |
| created_at | timestamp | |

### `audit_logs`
Tabla del módulo `audit_log` (nombre de módulo en singular, por convención
de paquete Python; tabla en plural, por convención SQL del resto del
esquema). Append-only, sin `updated_at` ni borrado.

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| clinic_id | FK clinics.id | Aísla la auditoría por clínica igual que el resto de entidades |
| actor_user_id | FK users.id | |
| action | string(64) | p. ej. `patient.created`, `patient.updated`, `patient.archived`, `patient.restored` |
| entity_type | string(64) | p. ej. `patient` |
| entity_id | UUID | |
| timestamp | timestamp | |
| request_id | string(64), nullable | Correlation ID de la petición HTTP que originó la acción (ver `architecture.md` §10) |
| metadata | JSONB, default `{}` | Mínima y segura: para `*.updated`, únicamente la lista de **nombres** de campos modificados (`{"changed_fields": ["display_name"]}`), nunca sus valores. Nunca cuerpos de petición, notas administrativas completas ni contenido clínico |

Nota de implementación: en el ORM, el atributo Python no puede llamarse
`metadata` (nombre reservado por `DeclarativeBase.metadata`); se mapea
como `audit_metadata` a la columna `metadata`.

### `consents`
| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| patient_id | FK patients.id | |
| clinical_session_id | FK clinical_sessions.id, nullable | |
| consent_type | enum | `grabacion_audio`, `procesamiento_ia`, `almacenamiento` |
| granted | bool | |
| granted_by | FK users.id | Quien registra el consentimiento en el sistema |
| recorded_at | timestamp | |
| notes | text, nullable | |

### `integration_configs`
Estado de activación de cada integración abstracta (todas `mock` en el
MVP), para preparar el interruptor futuro sin tocar código.

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| integration_name | enum | `transcription`, `language_model`, `patient_record`, `calendar` |
| active_provider | string | p. ej. `mock` |
| enabled | bool | |
| updated_by | FK users.id | |
| updated_at | timestamp | |

## 3. Campos de la anamnesis y sus estados

`current_content` / `ai_generated_content` de `anamnesis_documents`
almacenan un objeto con, como mínimo, estos campos. Cada campo tiene un
valor de texto (posiblemente vacío) **y** un estado independiente:

- `informado`
- `negado_explicitamente`
- `no_preguntado`
- `no_determinado`

Campos:

1. motivo_consulta
2. percepcion_subjetiva_perdida_auditiva
3. inicio_y_evolucion
4. lateralidad
5. antecedentes_familiares
6. antecedentes_otologicos
7. infecciones
8. cirugias
9. exposicion_ruido
10. medicacion_ototoxica_declarada
11. tinnitus
12. vertigo_o_inestabilidad
13. otalgia
14. otorrea
15. sensacion_plenitud
16. dificultades_comprension
17. situaciones_auditivas_problematicas
18. uso_previo_audifonos
19. expectativas
20. impacto_social_laboral_familiar
21. informacion_ausente (lista derivada: campos en `no_preguntado`)
22. observaciones_profesional (campo libre, **no generado por IA** — solo
    editable por el profesional)

Regla de generación: el `LanguageModelProvider` (incluido el mock) nunca
asigna `informado` a un campo sin una cita/fragmento de respaldo en la
transcripción. Si no hay evidencia textual, el campo queda en
`no_preguntado` o `no_determinado`.

## 4. Relaciones (resumen)

```
clinics 1───N users
clinics 1───N patients
clinics 1───N clinical_sessions
clinics 1───N audit_logs
patients 1───N clinical_sessions
clinical_sessions 1───1 audio_recordings   (MVP: un audio por sesión)
audio_recordings 1───1 transcriptions
clinical_sessions 1───1 anamnesis_documents
clinical_sessions 1───1 session_notes
clinical_sessions 1───N clinical_flags
clinical_sessions 1───N consents
anamnesis_documents / session_notes 1───N document_versions (por document_type + document_id)
users 1───N clinical_sessions (como professional_id, created_by, updated_by)
users 1───N patients (como created_by / updated_by)
users 1───N audit_logs (como actor)
```

## 5. Notas de diseño

- Se asume **un audio por sesión** en el MVP (simplifica el flujo); el
  modelo no impide extenderlo a N audios más adelante sin romper
  compatibilidad (bastaría con quitar la restricción de unicidad).
- `document_versions` usa una FK lógica (no de base de datos) a dos tablas
  distintas mediante `document_type` porque Postgres no soporta FKs
  polimórficas nativas; se documenta la integridad referencial como
  responsabilidad de la capa de aplicación y se cubre con tests.
- Ningún campo de `clinical_flags` ni `anamnesis_documents` contiene
  lenguaje diagnóstico; ver [clinical-safety.md](clinical-safety.md) para
  las reglas de redacción que debe cumplir el `LanguageModelProvider`.
- Ningún audio se almacena como blob en PostgreSQL: `audio_recordings`
  solo guarda metadatos, hash y una referencia opaca al proveedor de
  `AudioStorage`; el binario vive exclusivamente en ese proveedor
  (filesystem local en el MVP).

## 6. `ProcessingStatus`: estados de procesamiento y transiciones

Enumerado compartido (`core/processing_status.py`), con el subconjunto
aplicable a cada entidad. Validado en la capa de dominio/servicio (ver
[architecture.md](architecture.md) §5), no solo en la API.

> **Corrección de diseño (Fase 3):** las versiones anteriores de este
> documento incluían `clinical_sessions` como consumidor agregado de
> `ProcessingStatus` (`created → uploaded → … → exported`). Al diseñar en
> detalle el módulo `clinical_sessions` (Fase 3), ese enfoque genérico
> resultó insuficiente para expresar sus reglas de negocio propias
> (creación directa en varios estados, cancelación, revisión sin IA de
> por medio). `clinical_sessions` tiene ahora su **propia** máquina de
> estados, `ClinicalSessionStatus`, documentada en §8, independiente de
> `ProcessingStatus`. `ProcessingStatus` queda reservado a
> `audio_recordings`, `anamnesis_documents` y `session_notes` (fases
> futuras, sin implementar todavía).

| Estado | Aplica a | Significado |
|---|---|---|
| `uploaded` | `audio_recordings` | Audio recibido, pendiente de validar |
| `validating` | `audio_recordings` | Verificando tamaño/duración/extensión/MIME |
| `ready` | `audio_recordings` | Audio válido, listo para transcribir |
| `transcribing` | `audio_recordings` | Transcripción en curso |
| `transcribed` | `audio_recordings` | Transcripción completada |
| `generating` | `anamnesis_documents`, `session_notes` | Generación IA en curso |
| `review_pending` | `anamnesis_documents`, `session_notes` | Generado (o editado tras generar), pendiente de aprobación explícita |
| `approved` | `anamnesis_documents`, `session_notes` | Aprobado explícitamente por el profesional |
| `failed` | todas | Error no recuperable en el paso correspondiente; ver `failure_reason` |
| `deleted` | todas | `audio_recordings`: borrado físico + metadatos conservados. `anamnesis_documents`/`session_notes`: borrado **lógico** únicamente |

Transiciones válidas por entidad (cualquier otra transición debe ser
rechazada por la capa de dominio):

```
audio_recordings:
  uploaded → validating → ready → transcribing → transcribed
  (uploaded|validating) → failed
  ready → deleted   (retención, borrado físico manual)

anamnesis_documents / session_notes:
  generating → review_pending → approved
  review_pending → review_pending   (nueva edición, se versiona)
  approved → review_pending          (nueva edición tras aprobar: exige re-aprobación)
  generating → failed
  (review_pending|approved) → deleted  (borrado lógico, nunca físico si approved)
```

Un documento en `deleted` no aparece en las vistas por defecto pero
conserva su fila, `document_versions` y las entradas de `audit_log`
asociadas — nunca se elimina físicamente si alcanzó `approved`.

## 7. Multi-clínica, archivado de pacientes e índices (Fase 2)

**Multi-clínica desde el modelo, mono-clínica en el MVP.** Todas las
entidades con datos de negocio llevan `clinic_id` y toda consulta del
backend filtra explícitamente por la clínica del usuario autenticado
(`current_user.clinic_id`) — nunca se confía en un `clinic_id` recibido
del cliente. Ver `architecture.md` §9 (aislamiento por clínica) para el
mecanismo concreto.

**Archivado, no borrado físico.** `patients` no admite borrado físico vía
API. `is_archived` + `archived_at` sustituyen al borrado:

- **Archivar**: `is_archived = true`, `archived_at = now()`. Si el
  paciente ya estaba archivado, la operación es un no-op idempotente (no
  cambia nada, no genera una nueva entrada de auditoría).
- **Restaurar**: `is_archived = false`, `archived_at = null`. Si el
  paciente ya estaba activo, no-op idempotente por el mismo motivo.
- Un paciente archivado **no admite `PATCH`** salvo para restaurarlo
  primero (la API rechaza la edición con `409 Conflict`).
- El listado por defecto excluye archivados; el filtro `include_archived`
  los incluye explícitamente.

**Índices** (ver migración Alembic correspondiente):

| Índice | Tabla | Propósito |
|---|---|---|
| `UNIQUE (clinic_id, internal_code)` | `patients` | Unicidad de código interno por clínica (no global) |
| `(clinic_id, is_archived)` | `patients` | Listado filtrado por clínica y estado archivado |
| `(clinic_id, created_at)` | `patients` | Orden estable del listado paginado |
| `(clinic_id)` | `users` | Resolución de usuarios por clínica (seed, `CurrentUserProvider`) |
| `UNIQUE (email)` | `users` | Login futuro / resolución del usuario ficticio de desarrollo |
| `(entity_type, entity_id)` | `audit_logs` | Auditoría por entidad (p. ej. historial de un paciente) |
| `(actor_user_id)` | `audit_logs` | Auditoría por actor |
| `(clinic_id, timestamp)` | `audit_logs` | Auditoría por clínica y rango de fechas |

**`schema_version` en `patients`**: mismo patrón que en
`anamnesis_documents`/`session_notes` — versiona el esquema fijo de campos
administrativos del paciente para poder evolucionarlo sin migrar filas
existentes ni introducir formularios configurables por clínica.

## 8. `ClinicalSessionStatus`: máquina de estados de `clinical_sessions` (Fase 3)

**Independiente de `ProcessingStatus`** (§6) y de `is_archived` (que se
mantiene como eje separado, igual que en `patients` — ver justificación en
[product-requirements.md](product-requirements.md) §11, decisión 1).

### Estados

| Estado | Significado | ¿Terminal para `status`? |
|---|---|---|
| `scheduled` | Sesión programada, todavía no ha ocurrido | No |
| `in_progress` | La consulta está ocurriendo | No |
| `completed` | La consulta ha terminado | No |
| `review_pending` | Completada, pendiente de revisión explícita | No |
| `reviewed` | Revisada y cerrada | Sí |
| `cancelled` | No llegó a ocurrir / se interrumpió y no se retomará | Sí |

### Transiciones válidas

```
Creación (POST /clinical-sessions):
  → scheduled | in_progress | completed   (elegido explícitamente al crear;
                                             review_pending/reviewed/cancelled
                                             NO son valores iniciales válidos)

scheduled      → in_progress   (POST .../start)
scheduled      → cancelled     (POST .../cancel)
in_progress    → completed     (POST .../complete)
in_progress    → cancelled     (POST .../cancel)
completed      → review_pending (POST .../submit-review)
review_pending → reviewed      (POST .../review)

reviewed, cancelled: terminales — ninguna transición de `status` adicional
  (solo archivar, que no toca `status`).
```

Cualquier otra combinación origen→acción se rechaza con `409 Conflict`
(p. ej. `POST .../start` sobre una sesión `cancelled`).

### Idempotencia de las transiciones

Igual que `patients.archive`/`restore` (Fase 2): invocar una transición
cuyo estado de destino ya es el estado actual es un **no-op** (`200`, sin
nueva entrada de auditoría, sin modificar ninguna fecha ya fijada).
Invocar una transición desde un estado del que no puede alcanzarse ese
destino es un **conflicto** (`409`).

| Endpoint | No-op si ya está en | Conflicto si está en |
|---|---|---|
| `.../start` | `in_progress` | `completed`, `review_pending`, `reviewed`, `cancelled` |
| `.../complete` | `completed` | `scheduled`, `review_pending`, `reviewed`, `cancelled` |
| `.../submit-review` | `review_pending` | `scheduled`, `in_progress`, `reviewed`, `cancelled` |
| `.../review` | `reviewed` | `scheduled`, `in_progress`, `completed`, `cancelled` |
| `.../cancel` | `cancelled` | `completed`, `review_pending`, `reviewed` |
| `.../archive` | `is_archived = true` | Cualquier `status` fuera de `{completed, reviewed, cancelled}` |
| `.../restore` | `is_archived = false` | — |

### Efectos sobre fechas

`started_at`, `ended_at`, `reviewed_by` y `reviewed_at` son
**exclusivamente del servidor**: nunca se aceptan en el cuerpo de
`POST`/`PATCH` (no existen en esos esquemas de entrada bajo ninguna
circunstancia).

- **Creación directa en `in_progress`**: `started_at = now()`.
- **Creación directa en `completed`**: `started_at = ended_at = now()` —
  mismo instante en ambos campos, ya que el cliente no puede aportar esa
  distinción (no se acepta que la informe).
- **`.../start`** (`scheduled → in_progress`): `started_at = now()` si no
  estaba ya fijado (no-op idempotente si ya lo estaba: no se reescribe).
- **`.../complete`** (`in_progress → completed`): `ended_at = now()` si no
  estaba ya fijado.
- **`.../review`** (`review_pending → reviewed`): `reviewed_by =
  current_user.id`, `reviewed_at = now()`, ambos si no estaban ya
  fijados.
- `scheduled_at`: el único campo de fecha que aporta el cliente (opcional,
  en creación y, mientras sea editable, en `PATCH`); puede ser futura (es
  su propósito). Nunca se fija automáticamente.
- Ninguna fecha generada por el servidor puede ser futura. Ninguna
  transición ni reintento idempotente reescribe una fecha ya fijada por
  una transición anterior.

### Reglas de edición según estado (`PATCH`, incluido cambio de profesional)

| Estado | Editable vía `PATCH` |
|---|---|
| `scheduled`, `in_progress`, `completed` | `title`, `administrative_notes`, `session_type`, `scheduled_at`, y `professional_id` si quien edita tiene permiso de cambiar profesional |
| `review_pending` | **Únicamente** `title` y `administrative_notes` — cualquier otro campo en el payload (incluido `professional_id`, incluso siendo `admin`) devuelve `409` |
| `reviewed`, `cancelled` | Ninguno — `409` |
| Sesión archivada (cualquier `status`) | Ninguno — `409` |

`clinic_id`, `patient_id`, `status`, `started_at`, `ended_at`,
`reviewed_by` y `reviewed_at` nunca son editables vía `PATCH` bajo
ninguna circunstancia (no existen en el esquema de entrada); `status`
solo cambia mediante los endpoints de transición explícitos.

### Reglas de archivado

Mismo patrón que `patients` (borrado lógico únicamente, nunca físico):

- **Archivar**: solo permitido si `status ∈ {completed, reviewed,
  cancelled}` — **explícitamente no** desde `review_pending`
  (decisión cerrada: una revisión pendiente debe resolverse primero,
  vía `.../review`, o la sesión debe cancelarse si aplica antes de
  archivarse — no existe camino de cancelar desde `review_pending`, así
  que en la práctica debe alcanzar `reviewed`). Tampoco desde
  `scheduled`/`in_progress`. `status` no cambia al archivar.
- **Restaurar**: revierte `is_archived`; `status` no cambia — conserva
  exactamente el valor que tenía antes de archivar.
- Idempotente en ambos sentidos, igual que en `patients`.

## 9. Índices y restricciones de `clinical_sessions` (Fase 3)

| Índice / restricción | Propósito |
|---|---|
| `(clinic_id, patient_id)` | Listar sesiones de un paciente (vista de detalle de paciente) |
| `(clinic_id, professional_id)` | Filtro por profesional; comprobación de "sesiones propias" |
| `(clinic_id, status)` | Filtro por estado |
| `(clinic_id, session_type)` | Filtro por tipo |
| `(clinic_id, is_archived)` | Listado por defecto excluye archivadas |
| `(clinic_id, created_at)` | Orden estable del listado paginado |
| `(clinic_id, scheduled_at)` | Filtro por rango de fechas (ver limitación más abajo) |

**Invariantes de aplicación (no expresables como constraint de Postgres
sin triggers, por eso se validan en `service.py`, no en el esquema):**
`patient_id` debe pertenecer a `clinic_id`; `professional_id` debe
pertenecer a `clinic_id`, estar activo y tener rol `admin` o
`audiologist`. Decisión cerrada: se validan exclusivamente en el
servicio, sin trigger de base de datos (ver
[product-requirements.md](product-requirements.md) §11, decisión 14).

**Limitación conocida y aceptada del filtro de fechas**: `scheduled_at`
es nulo en sesiones creadas directamente como `in_progress`/`completed`
sin haber sido programadas — esas sesiones no aparecerán en el filtro
`scheduled_from`/`scheduled_to` (parámetros de query, ver
[api-specification.md](api-specification.md) §Clinical sessions).
Decisión cerrada: no se crea una fecha "efectiva" combinada (ver
[product-requirements.md](product-requirements.md) §11, decisión 13).
