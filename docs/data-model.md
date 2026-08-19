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
| schema_version | int, default 1 | Versión del esquema fijo de campos de `patients`, análogo a `ai_artifacts.schema_version` |

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

### `ai_artifacts`, `ai_artifact_versions`, `ai_generation_runs`, `ai_pipeline_runs`, `prompt_templates`

**Sustituyen por completo** a `transcriptions`, `anamnesis_documents`,
`session_notes` y `document_versions` del diseño anterior (eliminadas de
esta documentación, no quedan tablas alternativas para el mismo
propósito). Diseño cerrado en la Fase 4 — ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) para el
análisis completo (por qué una entidad genérica `AIArtifact` en vez de
una tabla por tipo de artefacto, interfaces, orquestador, contratos).
`clinical_flags` (más abajo) no se sustituye: sigue siendo la tabla de
disposición por ítem, ahora alimentada por `ai_artifact_versions` en vez
de generarse de forma aislada.

#### `ai_artifacts`
Un sobre por (sesión, tipo de artefacto) — como mucho uno activo por
combinación. Regenerar no crea una fila nueva aquí, crea una versión
nueva en `ai_artifact_versions`.

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| clinical_session_id | FK clinical_sessions.id | |
| artifact_type | enum (`AIArtifactType`) | `transcript`, `summary`, `clinical_flags`, `missing_information`, `anamnesis`, `patient_summary` (contrato cerrado en el hito 6.2 — RFC v2 §4.3; no producido en producción hasta el hito 6.3) |
| status | enum (`AIArtifactStatus`) | `review_pending`, `approved`, `rejected` — ver §10 |
| current_version_id | FK ai_artifact_versions.id | La versión vigente; nunca nulo tras la creación |
| confidence | int, nullable | 0-100; espejo desnormalizado de `current_version.confidence`, actualizado en la misma transacción que `current_version_id`. Nunca se usa para aprobar automáticamente — ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §8 |
| schema_version | int, default 1 | Versión del esquema JSON de `content` para este `artifact_type` — mismo patrón que `patients.schema_version` |
| approved_by | FK users.id, nullable | |
| approved_at | timestamp, nullable | |
| rejected_by | FK users.id, nullable | |
| rejected_at | timestamp, nullable | |
| rejection_reason | text, nullable | |
| deleted_by | FK users.id, nullable | Borrado **lógico únicamente**; un artefacto `approved` nunca se elimina físicamente |
| deleted_at | timestamp, nullable | |
| created_at / updated_at | timestamp | |

`UNIQUE (clinical_session_id, artifact_type)`.

#### `ai_artifact_versions`
Append-only: nunca se edita ni se borra una fila existente.

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| ai_artifact_id | FK ai_artifacts.id | |
| version_number | int | Monótono por `ai_artifact_id`, empieza en 1 |
| content | JSONB | Forma específica de `artifact_type`, validada en `service.py` por un esquema propio de cada tipo — ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.1 (principio "JSON First": nunca texto libre ni Markdown como contrato interno) |
| confidence | int, nullable | 0-100; solo si `source = ai_generated` — `null` si `human_edited` |
| source_map | JSONB, nullable | Trazabilidad de cada fragmento generado hacia su origen (rango de transcripción, segmento de audio, timestamps, offsets). Diseño preparado, **no poblado todavía** — ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.7 |
| source | enum (`AIArtifactVersionSource`) | `ai_generated`, `human_edited` |
| generation_run_id | FK ai_generation_runs.id, nullable | Solo si `source = ai_generated` |
| created_by | FK users.id, nullable | Nulo si `ai_generated`; siempre presente si `human_edited` |
| change_note | text, nullable | Comentario opcional del profesional |
| created_at | timestamp | |

`UNIQUE (ai_artifact_id, version_number)`.

#### `ai_generation_runs`
Una fila por ejecución de un paso del pipeline — la auditoría técnica de
cada generación (nunca contenido clínico ni secretos, ver
[privacy-and-security.md](privacy-and-security.md) §6).

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| ai_pipeline_run_id | FK ai_pipeline_runs.id | Agrupa todos los pasos de una ejecución completa |
| clinical_session_id | FK clinical_sessions.id | Denormalizado, útil si el paso falla antes de crear artefacto |
| artifact_type | enum (`AIArtifactType`) | Qué paso es |
| ai_artifact_id | FK ai_artifacts.id, nullable | Nulo si el paso falló antes de producir contenido |
| resulting_version_number | int, nullable | Qué `ai_artifact_versions.version_number` produjo esta ejecución |
| status | enum (`AIGenerationRunStatus`) | `queued`, `processing`, `completed`, `failed` — ver §10 |
| provider_name | string | p. ej. `mock`; futuro `openai`/`anthropic`/... |
| model_name | string, nullable | p. ej. `mock-v1` |
| prompt_template_id | FK prompt_templates.id, nullable | Nulo para `TranscriptionProvider` (no usa plantillas de LLM) |
| prompt_template_version | int, nullable | Copiado en el momento de la ejecución — si la plantilla se republica después, esta fila sigue apuntando a la versión realmente usada |
| input_token_count | int, nullable | Vía `TokenCounter`, o del proveedor si lo devuelve |
| output_token_count | int, nullable | |
| estimated_cost_usd | numeric(10,6), nullable | Vía `CostEstimator` |
| latency_ms | int, nullable | Duración de la llamada al proveedor |
| execution_time_ms | int, nullable | Duración total del paso (incluye render de prompt, parseo, persistencia — puede ser mayor que `latency_ms`) |
| rendered_system_prompt | text, nullable | **Solo si** `Settings.ai_store_rendered_prompts = true` (config, `false` por defecto); `NULL` en caso contrario, sin excepción — ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.5 |
| rendered_user_prompt | text, nullable | Idem |
| raw_response | JSONB, nullable | Idem |
| started_at | timestamp | |
| completed_at | timestamp, nullable | |
| failure_reason | text, nullable | |
| request_id | string, nullable | Correlation ID, mismo patrón que `audit_logs.request_id` |

**Nunca almacena**: secretos, claves de API. **No almacena** el prompt
renderizado ni la respuesta cruda salvo activación explícita por
configuración (columnas de arriba) — ver implicaciones de privacidad en
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.5.

#### `ai_pipeline_runs`
Una fila por disparo completo del pipeline (una ejecución de
`POST .../ai/generate`).

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| clinical_session_id | FK clinical_sessions.id | |
| triggered_by | FK users.id | |
| status | enum (`AIPipelineRunStatus`) | `queued`, `processing`, `completed`, `failed`, `partially_failed` |
| started_at | timestamp | |
| completed_at | timestamp, nullable | |
| request_id | string, nullable | |

#### `prompt_templates`
Ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.4 para
la arquitectura completa de gestión de prompts (origen dual: fixtures en
git → seed → base de datos).

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| name | string | p. ej. `anamnesis.generate`, `summary.generate` — por propósito, no por proveedor |
| version | int | Monótono por `name`, append-only |
| description | text, nullable | |
| system_prompt | text, nullable | |
| user_prompt_template | text | Con marcadores `{{variable}}` |
| variables_schema | JSONB | Nombres/tipos de variables esperadas; se valida antes de renderizar |
| is_active | bool | Exactamente una versión activa por `name` |
| created_by | FK users.id | |
| change_note | text, nullable | |
| created_at | timestamp | |

`UNIQUE (name, version)`; índice parcial `UNIQUE (name) WHERE is_active`.

### `clinical_flags`
| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| clinical_session_id | FK clinical_sessions.id | |
| category | string | p. ej. `otalgia`, `perdida_asimetrica`, `tinnitus_unilateral` |
| description | text | Redactado en lenguaje no diagnóstico (ver clinical-safety.md) |
| source_excerpt | text, nullable | Fragmento de la transcripción que originó la señal |
| ruleset_name | string | p. ej. `demo_generic_v1`; identifica qué `ClinicalFlagsGenerator` la generó, para trazabilidad si se sustituye por un protocolo validado |
| status | enum | `sugerida_ia`, `confirmada_por_profesional`, `descartada` — eje de disposición del profesional, independiente de los estados del AI Pipeline (ver §10 y architecture.md §5) |
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
Implementada en la Fase 6 (hito 6.0) como módulo propio `consents`
(dominio + infraestructura, sin servicio ni endpoint todavía — ver
[fase-6-rfc.md](fase-6-rfc.md) §9.1 y §10, hito 6.0). `clinic_id` se
añade respecto al diseño original para mantener el mismo aislamiento por
clínica que el resto de entidades clínicas (`patients`,
`clinical_sessions`, `ai_artifacts`, `audit_logs`), en vez de resolverlo
por join a través de `patients`.

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| clinic_id | FK clinics.id | Aísla por clínica igual que el resto de entidades clínicas |
| patient_id | FK patients.id | |
| clinical_session_id | FK clinical_sessions.id, nullable | |
| consent_type | enum | `grabacion_audio`, `procesamiento_ia`, `almacenamiento` |
| granted | bool | |
| consent_version | string, nullable | Versión de la política de consentimiento aceptada. Para `procesamiento_ia`, un consentimiento solo es válido si `consent_version` coincide con la versión vigente configurada (`AI_PROCESSING_CONSENT_VERSION`) — ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.3 |
| granted_by | FK users.id | Quien registra el consentimiento en el sistema |
| recorded_at | timestamp | Cumple el rol de "consent_timestamp" |
| notes | text, nullable | |

`AIPipelineService.run_pipeline` comprueba el consentimiento de
`procesamiento_ia` cuando `AI_PROCESSING_CONSENT_ENFORCED=true`
(por defecto `false` en esta fase, ya que todos los proveedores de
`run_pipeline` siguen siendo `Mock` — activar la comprobación no cambia
ningún test existente). Sin un registro `granted=true` con la
`consent_version` vigente, la llamada falla con `ConflictError` antes de
crear ningún `AIPipelineRun`. No existe todavía endpoint para conceder
consentimiento — es infraestructura preparada para cuando el hito 6.3
active un proveedor LLM real.

### `integration_configs`
Estado de activación de cada integración abstracta (todas `mock` en el
MVP), para preparar el interruptor futuro sin tocar código. Sin
`clinic_id` propio: configuración global de aplicación, no por clínica —
excepción deliberada al aislamiento por clínica del resto del esquema,
consistente con la exclusión de multi-tenant del MVP (ver
[architecture.md](architecture.md) §10). Cualquier `admin` de cualquier
clínica puede leer/editar.

**Corrección (Fase 7.3):** el diseño original de esta tabla listaba
cuatro valores posibles de `integration_name` (`transcription`,
`language_model`, `patient_record`, `calendar`). Se reduce a **dos**
(`patient_record`, `calendar`) — mismo criterio ya aplicado a la
corrección `clinician` → `audiologist` de la Fase 7.1
([api-specification.md](api-specification.md)): la tabla solo cubre
integraciones sin implementación real todavía. `transcription` y
`language_model` ya tienen proveedores reales desde las Fases 5 y 6.3
respectivamente, y se seleccionan por variable de entorno (`Settings`,
ver [architecture.md](architecture.md) §4), no por esta tabla —
incluirlos aquí crearía una segunda fuente de verdad que no controlaría
nada real.

| Campo | Tipo | Notas |
|---|---|---|
| id | UUID PK | |
| integration_name | enum | `patient_record`, `calendar` |
| active_provider | string | p. ej. `mock` — único valor válido en el MVP |
| enabled | bool | |
| updated_by | FK users.id | |
| updated_at | timestamp | |

## 3. Campos de la anamnesis y sus estados

`ai_artifact_versions.content` de la versión vigente de un `ai_artifacts`
con `artifact_type = anamnesis` (ver §2) almacena un objeto con
exactamente los 20 campos de `ANAMNESIS_FIELDS`
(`app/integrations/domain/anamnesis_generator.py`) — antes vivía en
`anamnesis_documents.current_content`/`ai_generated_content`, tabla ya
eliminada de este documento (ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md)).
Cada campo tiene un valor de texto (posiblemente vacío) **y** un estado
independiente:

- `informado`
- `negado_explicitamente`
- `no_preguntado`
- `no_determinado`

Los 20 campos generados por IA (`ANAMNESIS_FIELDS`, forma canónica
cerrada por [fase-6-rfc.md](fase-6-rfc.md) §0/§11.1 — esta fase no
introduce una variante de 22 campos):

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

Dos campos administrativos adicionales, **fuera** del objeto anterior y
**no generados por IA** — no forman parte del `content` de la versión ni
de `ANAMNESIS_FIELDS`:

- `informacion_ausente`: lista derivada, calculada por el backend a
  partir de los campos en `no_preguntado`; distinta de la lista de
  sugerencias de seguimiento del artefacto `missing_information`,
  generado antes que la anamnesis y usado como una de sus entradas — ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §1.3.
- `observaciones_profesional`: campo libre, exclusivamente editable por
  el profesional.

Ninguno de los dos está implementado todavía (sin cálculo de
`informacion_ausente` ni campo editable `observaciones_profesional` en el
backend); se documentan aquí como diseño no implementado, no como salida
de `AnamnesisGenerator`.

Regla de generación: `AnamnesisGenerator` (incluido el mock) nunca asigna
`informado` a un campo sin una cita/fragmento de respaldo en la
transcripción. Si no hay evidencia textual, el campo queda en
`no_preguntado` o `no_determinado`.

## 4. Relaciones (resumen)

```
clinics 1───N users
clinics 1───N patients
clinics 1───N clinical_sessions
clinics 1───N audit_logs
patients 1───N clinical_sessions
patients 1───N consents
clinical_sessions 1───1 audio_recordings     (MVP: un audio por sesión)
clinical_sessions 1───N ai_artifacts          (a lo sumo 1 por artifact_type, vía UNIQUE)
ai_artifacts 1───N ai_artifact_versions
ai_artifacts N───1 ai_artifact_versions        (current_version_id, la vigente)
ai_artifact_versions N───1 ai_generation_runs   (0..1, nulo si human_edited)
clinical_sessions 1───N ai_pipeline_runs
ai_pipeline_runs 1───N ai_generation_runs
ai_generation_runs N───1 prompt_templates         (0..1)
clinical_sessions 1───N clinical_flags             (alimentada por
                                                      ai_artifact_versions.content
                                                      cuando artifact_type = clinical_flags)
clinical_sessions 1───N consents
users 1───N clinical_sessions (como professional_id, created_by, updated_by)
users 1───N patients (como created_by / updated_by)
users 1───N audit_logs (como actor)
users 1───N ai_pipeline_runs (como triggered_by)
```

## 5. Notas de diseño

- Se asume **un audio por sesión** en el MVP (simplifica el flujo); el
  modelo no impide extenderlo a N audios más adelante sin romper
  compatibilidad (bastaría con quitar la restricción de unicidad).
- `ai_artifact_versions` es append-only y versiona por igual las cinco
  variantes de artefacto de IA (transcripción, resumen, señales de
  alerta, información ausente, anamnesis) — sustituye a la antigua
  `document_versions` (que usaba una FK lógica polimórfica solo para dos
  tipos) por un único mecanismo compartido por todos. Ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §3.1 para el
  análisis de por qué se prefirió una entidad genérica a una tabla por
  tipo de artefacto.
- Ningún campo de `clinical_flags` ni de `ai_artifact_versions.content`
  (cuando `artifact_type = anamnesis`) contiene lenguaje diagnóstico; ver
  [clinical-safety.md](clinical-safety.md) para las reglas de redacción
  que deben cumplir `AnamnesisGenerator`/`ClinicalFlagsGenerator`.
- Ningún audio se almacena como blob en PostgreSQL: `audio_recordings`
  solo guarda metadatos, hash y una referencia opaca al proveedor de
  `AudioStorage`; el binario vive exclusivamente en ese proveedor
  (filesystem local en el MVP).

## 6. `ProcessingStatus`: estados de procesamiento y transiciones

Enumerado compartido (`core/processing_status.py`), con el subconjunto
aplicable a cada entidad. Validado en la capa de dominio/servicio (ver
[architecture.md](architecture.md) §5), no solo en la API.

> **Corrección de diseño (Fase 3, ampliada en Fase 4):** las versiones
> anteriores de este documento incluían `clinical_sessions` como
> consumidor agregado de `ProcessingStatus` (`created → uploaded → … →
> exported`). Al diseñar en detalle el módulo `clinical_sessions`
> (Fase 3), ese enfoque genérico resultó insuficiente para expresar sus
> reglas de negocio propias. `clinical_sessions` tiene su **propia**
> máquina de estados, `ClinicalSessionStatus`, documentada en §8,
> independiente de `ProcessingStatus`. El diseño previo también reservaba
> `ProcessingStatus` para `anamnesis_documents`/`session_notes`
> (fases futuras, nunca implementadas); esas tablas se eliminaron en la
> Fase 4 en favor de `ai_artifacts`/`ai_artifact_versions` (§2), que usan
> su **propio** modelo de estados en dos ejes independientes
> (`AIArtifactStatus`/`AIGenerationRunStatus`, ver §10) — tampoco
> `ProcessingStatus`. **`ProcessingStatus` queda reservado
> exclusivamente a `audio_recordings`** (única entidad que sigue
> aplicándolo; fase futura, sin implementar todavía).

| Estado | Aplica a | Significado |
|---|---|---|
| `uploaded` | `audio_recordings` | Audio recibido, pendiente de validar |
| `validating` | `audio_recordings` | Verificando tamaño/duración/extensión/MIME |
| `ready` | `audio_recordings` | Audio válido, listo para transcribir |
| `transcribing` | `audio_recordings` | Transcripción en curso |
| `transcribed` | `audio_recordings` | Transcripción completada |
| `failed` | `audio_recordings` | Error no recuperable en el paso correspondiente; ver `failure_reason` |
| `deleted` | `audio_recordings` | Borrado físico + metadatos conservados |

Transiciones válidas (cualquier otra transición debe ser rechazada por la
capa de dominio):

```
audio_recordings:
  uploaded → validating → ready → transcribing → transcribed
  (uploaded|validating) → failed
  ready → deleted   (retención, borrado físico manual)
```

Ver §10 para los estados de los artefactos de IA generados a partir de la
transcripción (`ai_artifacts`/`ai_generation_runs`), que sustituyen al
antiguo uso de `ProcessingStatus` para `anamnesis_documents`/`session_notes`.

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
`ai_artifacts` — versiona el esquema fijo de campos
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

## 10. Estados del AI Pipeline (Fase 4)

Diseño cerrado el 2026-08-10 — análisis completo y justificación en
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §9.2 y §12.
Dos ejes **independientes**, nunca mezclados en un único enumerado:

### `AIGenerationRunStatus` — eje de ejecución (`ai_generation_runs.status`)

| Estado | Significado | ¿Terminal? |
|---|---|---|
| `queued` | Paso encolado, todavía no iniciado | No |
| `processing` | Ejecutándose (llamada al provider en curso) | No |
| `completed` | Terminó con éxito; produjo una `ai_artifact_versions` | Sí |
| `failed` | Terminó con error; ver `failure_reason` | Sí |

```
queued → processing → completed
                    → failed
```

No existe un estado `created` distinto de `queued` (un
`ai_generation_runs` nace directamente en `queued`; no hay hueco
intermedio en un orquestador síncrono).

### `AIArtifactStatus` — eje de disposición humana (`ai_artifacts.status`)

| Estado | Significado | ¿Terminal? |
|---|---|---|
| `review_pending` | Existe una versión vigente sin decisión humana, o ya se editó/regeneró desde `approved`/`rejected` | No |
| `approved` | Aprobado explícitamente por un profesional | No (una nueva edición lo devuelve a `review_pending`) |
| `rejected` | Rechazado explícitamente; puede reabrirse mediante edición o regeneración | No |

```
              ┌──────────────────────────────┐
              ▼                              │
  review_pending → approved ──────────────────┤ (editar tras aprobar)
              │                              │
              └→ rejected ────────────────────┘ (editar/regenerar tras rechazar)
```

No existe `failed` en este eje (pertenece únicamente al eje de
ejecución: si una regeneración falla, el `AIArtifact` existente no se
toca). No existe `versioned` como estado: todo `AIArtifact` tiene ≥1
versión desde que existe, es un hecho estructural, no un estado — mismo
criterio que `clinical_sessions` no tiene un estado "ha sido creada".

### `AIPipelineRunStatus` — agregado de una ejecución completa (`ai_pipeline_runs.status`)

| Estado | Significado |
|---|---|
| `queued` | Disparado, todavía no iniciado |
| `processing` | Al menos un paso en curso |
| `completed` | Todos los pasos completaron |
| `partially_failed` | Al menos un paso falló o se saltó, pero al menos uno completó |
| `failed` | Ningún paso completó |

### `confidence`

`ai_artifacts.confidence` / `ai_artifact_versions.confidence` (0-100):
confianza estimada del modelo en la generación, **nunca** sustituye al
criterio clínico ni decide ninguna transición de forma automática —
ninguna ruta de código aprueba un artefacto por su valor de `confidence`.
Solo se usa para resaltar en la interfaz qué elementos merecen especial
atención en la revisión humana. Ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §8.

## 11. Índices y restricciones del AI Pipeline (Fase 4)

| Índice / restricción | Tabla | Propósito |
|---|---|---|
| `UNIQUE (clinical_session_id, artifact_type)` | `ai_artifacts` | A lo sumo un artefacto activo por tipo y sesión |
| `(clinical_session_id)` | `ai_artifacts` | Listar todos los artefactos de una sesión |
| `UNIQUE (ai_artifact_id, version_number)` | `ai_artifact_versions` | Integridad del versionado |
| `(ai_artifact_id, version_number DESC)` | `ai_artifact_versions` | Obtener el historial ordenado |
| `(ai_pipeline_run_id)` | `ai_generation_runs` | Listar los pasos de una ejecución |
| `(clinical_session_id, artifact_type)` | `ai_generation_runs` | Auditoría técnica por sesión y tipo |
| `(clinical_session_id, status)` | `ai_pipeline_runs` | Comprobar si ya existe una ejecución `queued`/`processing` en curso (ver regla de concurrencia en [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §8) |
| `UNIQUE (name, version)` | `prompt_templates` | Integridad del versionado de plantillas |
| `UNIQUE (name) WHERE is_active` | `prompt_templates` | Exactamente una versión activa por nombre |

**Invariante de aplicación**: un `ai_pipeline_runs` con `status IN
(queued, processing)` para una `clinical_session_id` dada bloquea un
nuevo disparo del pipeline sobre esa misma sesión (`ConflictError` →
409) — validado en `AIPipelineService`, no mediante constraint de
Postgres, mismo criterio ya aplicado a las invariantes de
`clinical_sessions` (§9).
