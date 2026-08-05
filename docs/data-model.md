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

### `patients`
| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| display_name | string | Nombre ficticio para uso en UI |
| date_of_birth | date, nullable | Ficticia |
| internal_reference | string, único | Referencia interna, no un identificador sanitario real |
| is_fictional | bool, default true | Salvaguarda explícita; el MVP no permite `false` |
| created_at / updated_at | timestamp | |
| created_by | FK users.id | |

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

### `users`
| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| email | string, único | |
| full_name | string | |
| role | enum | `admin`, `clinician` |
| hashed_password | string | Nunca en texto plano; hashing en `core/security.py` |
| is_active | bool | |
| created_at | timestamp | |

### `audit_log`
Append-only, sin `updated_at` ni borrado.

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| actor_user_id | FK users.id | |
| action | string | p. ej. `patient.created`, `anamnesis.approved`, `audio.uploaded` |
| entity_type | string | |
| entity_id | UUID | |
| metadata | JSONB, nullable | Detalles adicionales, nunca contenido clínico completo |
| occurred_at | timestamp | |

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
patients 1───N clinical_sessions
clinical_sessions 1───1 audio_recordings   (MVP: un audio por sesión)
audio_recordings 1───1 transcriptions
clinical_sessions 1───1 anamnesis_documents
clinical_sessions 1───1 session_notes
clinical_sessions 1───N clinical_flags
clinical_sessions 1───N consents
anamnesis_documents / session_notes 1───N document_versions (por document_type + document_id)
users 1───N clinical_sessions (como clinician)
users 1───N audit_log (como actor)
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
