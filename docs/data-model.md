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
| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| patient_id | FK patients.id | |
| clinician_id | FK users.id | Profesional responsable único (sin edición colaborativa) |
| status | enum (`ProcessingStatus`) | `created`, `uploaded`, `validating`, `ready`, `transcribing`, `transcribed`, `generating`, `review_pending`, `approved`, `exported`, `failed`, `deleted` — ver §6 |
| session_date | timestamp | |
| notes | text, nullable | Notas libres del profesional, no generadas por IA |
| deleted_at | timestamp, nullable | Borrado lógico; nunca se elimina la fila |
| created_at / updated_at | timestamp | |

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
clinics 1───N audit_logs
patients 1───N clinical_sessions
clinical_sessions 1───1 audio_recordings   (MVP: un audio por sesión)
audio_recordings 1───1 transcriptions
clinical_sessions 1───1 anamnesis_documents
clinical_sessions 1───1 session_notes
clinical_sessions 1───N clinical_flags
clinical_sessions 1───N consents
anamnesis_documents / session_notes 1───N document_versions (por document_type + document_id)
users 1───N clinical_sessions (como clinician)
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

| Estado | Aplica a | Significado |
|---|---|---|
| `created` | `clinical_sessions` | Sesión creada, sin audio todavía |
| `uploaded` | `clinical_sessions`, `audio_recordings` | Audio recibido, pendiente de validar |
| `validating` | `clinical_sessions`, `audio_recordings` | Verificando tamaño/duración/extensión/MIME |
| `ready` | `clinical_sessions`, `audio_recordings` | Audio válido, listo para transcribir |
| `transcribing` | `clinical_sessions`, `audio_recordings` | Transcripción en curso |
| `transcribed` | `clinical_sessions`, `audio_recordings` | Transcripción completada |
| `generating` | `clinical_sessions`, `anamnesis_documents`, `session_notes` | Generación IA en curso |
| `review_pending` | `clinical_sessions`, `anamnesis_documents`, `session_notes` | Generado (o editado tras generar), pendiente de aprobación explícita |
| `approved` | `clinical_sessions`, `anamnesis_documents`, `session_notes` | Aprobado explícitamente por el profesional |
| `exported` | `clinical_sessions` | Al menos un documento aprobado se ha exportado (informativo, no bloqueante) |
| `failed` | todas | Error no recuperable en el paso correspondiente; ver `failure_reason` |
| `deleted` | todas | `audio_recordings`: borrado físico + metadatos conservados. `anamnesis_documents`/`session_notes`/`clinical_sessions`: borrado **lógico** únicamente |

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

clinical_sessions (agregado, informativo):
  created → uploaded → validating → ready → transcribing → transcribed
    → generating → review_pending → approved → exported
  cualquier estado → failed | deleted
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
