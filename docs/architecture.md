# Arquitectura — Audiology AI Assistant

## 1. Vista general

```
┌─────────────────────────┐        HTTPS/JSON        ┌──────────────────────────────┐
│   Frontend (React/TS)   │ ────────────────────────▶ │   Backend (FastAPI, Python)  │
│   Vite, pantallas por   │ ◀──────────────────────── │   Módulos por dominio        │
│   flujo clínico         │                            │                              │
└─────────────────────────┘                            └───────────────┬──────────────┘
                                                                         │
                                                          ┌──────────────┴──────────────┐
                                                          │        PostgreSQL           │
                                                          └──────────────────────────────┘

Backend, capa de integración:
  integrations/    → TranscriptionProvider ──▶ MockTranscriptionProvider (MVP)
                                             ──▶ AssemblyAITranscriptionProvider (Fase 5,
                                                 real; selección por TRANSCRIPTION_PROVIDER,
                                                 ver integrations/factory.py)
                    → LanguageModelProvider ──▶ MockLanguageModelProvider (MVP)
                    → SummaryGenerator ──▶ MockSummaryGenerator (MVP)
                    → ClinicalFlagsGenerator ──▶ MockClinicalFlagsGenerator (MVP, checklist basado en reglas)
                    → MissingInformationGenerator ──▶ MockMissingInformationGenerator (MVP)
                    → AnamnesisGenerator ──▶ MockAnamnesisGenerator (MVP)
                    → CostEstimator ──▶ MockCostEstimator (MVP)
                    → TokenCounter ──▶ MockTokenCounter (MVP)
                    → PatientRecordIntegration ──▶ MockPatientRecordIntegration (MVP)
                    → CalendarIntegration ──▶ MockCalendarIntegration (MVP)
  ai_pipeline/ (exportación de un artefacto aprobado) → DocumentExporter
                    ──▶ PdfDocumentExporter / TextDocumentExporter
```

Todo proveedor externo (transcripción, LLM, historia clínica, calendario) se
consume **siempre** a través de una interfaz abstracta. El MVP solo registra
implementaciones `Mock*`. Cambiar a un proveedor real en el futuro no debe
requerir tocar los módulos de dominio, solo añadir una nueva implementación
y configurarla.

## 2. Principio de capas (backend)

Cada módulo se organiza en tres capas:

- **domain/**: entidades, reglas de negocio, interfaces (puertos). Sin
  dependencias de FastAPI, SQLAlchemy ni librerías externas.
- **infrastructure/**: implementación de persistencia (repositorios
  SQLAlchemy), implementaciones concretas de proveedores (`Mock*`),
  adaptadores a servicios externos.
- **presentation/** (o `api/`): routers FastAPI, esquemas Pydantic de
  entrada/salida, mapeo entre DTO y dominio.

Regla de dependencia: `presentation → domain ← infrastructure`. El dominio
no importa nada de infraestructura ni de presentación.

```
backend/
  app/
    clinics/
      domain/          # entidad Clinic (dataclass, sin SQLAlchemy)
      infrastructure/  # ORM + repositorio; sin API propia en la Fase 2
    users/
      domain/          # entidad User, enum Role
      infrastructure/  # ORM + repositorio; sin API propia en la Fase 2
    audit_log/
      domain/          # entidad AuditLogEntry
      infrastructure/  # ORM (tabla audit_logs) + repositorio
    patients/
      domain/
        entities.py     # Patient (dataclass), Sex (enum)
        repository.py   # interfaz PatientRepository (puerto)
      infrastructure/
        orm.py           # PatientORM (SQLAlchemy)
        repository.py    # SqlAlchemyPatientRepository
      service.py         # PatientService: autoriza → opera → audita → commit
      api/
        schemas.py        # Pydantic, separados del ORM
        router.py          # /api/v1/patients/*
    clinical_sessions/
      domain/
        entities.py      # ClinicalSession (dataclass), SessionType, ClinicalSessionStatus (enums)
        state_machine.py  # transiciones válidas de ClinicalSessionStatus; independiente de ProcessingStatus
        repository.py      # interfaz ClinicalSessionRepository (puerto)
      infrastructure/
        orm.py               # ClinicalSessionORM (SQLAlchemy)
        repository.py         # SqlAlchemyClinicalSessionRepository
      service.py              # ClinicalSessionService: autoriza → valida transición → opera → audita → commit
      api/
        schemas.py             # Pydantic, separados del ORM
        router.py                # /api/v1/clinical-sessions/*
    audio/                           # Fase 5 — ver development-plan.md
      domain/
        entities.py                   # AudioRecording (dataclass)
        audio_storage.py                # interfaz AudioStorage (puerto)
        validation.py                    # reglas de tamaño/duración/extensión/MIME
        repository.py                     # interfaz AudioRecordingRepository (puerto)
                                           # (RetentionCleanupService NO vive aquí — ver
                                           # nota tras este árbol y app/retention/, Fase 7.2)
      infrastructure/
        orm.py                          # AudioRecordingORM
        repository.py                     # SqlAlchemyAudioRecordingRepository
        local_audio_storage.py             # única implementación de AudioStorage
      service.py                          # AudioRecordingService: autoriza →
                                           # valida → almacena → audita → commit
      api/
        schemas.py
        router.py                          # /api/v1/clinical-sessions/{id}/audio-recordings,
                                            # /api/v1/audio-recordings/{id}
    ai_pipeline/                    # Fase 4 — diseño cerrado en
                                     # ai-pipeline-architecture.md; sustituye
                                     # por completo a los antiguos módulos
                                     # transcription/anamnesis/session_notes
                                     # (nunca implementados)
      domain/
        entities.py                  # AIArtifact, AIArtifactVersion,
                                      # AIGenerationRun, AIPipelineRun,
                                      # PipelineResult, enums
        artifact_repository.py        # interfaz AIArtifactRepository (puerto)
        generation_run_repository.py   # interfaz (puerto)
        pipeline_run_repository.py      # interfaz (puerto)
        prompt_template_repository.py    # interfaz (puerto)
        prompt_renderer.py                # PromptRenderer — interno, no es
                                           # una integración externa (mismo
                                           # criterio que AudioStorage)
        pipeline.py                        # PipelineOrchestrator (puerto) +
                                            # SequentialPipelineOrchestrator
        steps/                              # un PipelineStep por artifact_type
          transcription_step.py
          summary_step.py
          clinical_flags_step.py
          missing_information_step.py
          anamnesis_step.py
      infrastructure/
        orm.py                          # AIArtifactORM, AIArtifactVersionORM,
                                         # AIGenerationRunORM, AIPipelineRunORM,
                                         # PromptTemplateORM
        repository.py                    # implementaciones SQLAlchemy
      service.py                          # AIPipelineService: autoriza →
                                           # ejecuta el pipeline → persiste →
                                           # audita → commit
      api/
        schemas.py
        router.py                          # /api/v1/clinical-sessions/{id}/ai/*
    clinical_flags/                   # disposición por ítem (confirmar/
                                       # descartar); no genera contenido —
                                       # eso lo hace ClinicalFlagsGenerator
                                       # en integrations/, orquestado por
                                       # ai_pipeline/
      domain/
        entities.py                    # ClinicalFlag (dataclass), enum de disposición
        repository.py                   # interfaz ClinicalFlagRepository (puerto)
      infrastructure/
        orm.py
        repository.py
      service.py                        # confirma/descarta; autoriza → opera → audita
      api/
        schemas.py
        router.py                        # PATCH /clinical-flags/{flag_id}
    integrations/
      domain/            # interfaces abstractas compartidas
        transcription_provider.py       # TranscriptionProvider
        language_model_provider.py       # LanguageModelProvider (bajo nivel,
                                          # compuesto por los *Generator)
        summary_generator.py              # SummaryGenerator
        clinical_flags_generator.py        # ClinicalFlagsGenerator (MVP:
                                            # basado en reglas, sin LLM)
        missing_information_generator.py    # MissingInformationGenerator
        anamnesis_generator.py               # AnamnesisGenerator
        cost_estimator.py                     # CostEstimator
        token_counter.py                       # TokenCounter
        patient_record_integration.py
        calendar_integration.py
        document_exporter.py
      mocks/
        mock_transcription_provider.py
        mock_language_model_provider.py
        mock_summary_generator.py
        mock_clinical_flags_generator.py
        mock_missing_information_generator.py
        mock_anamnesis_generator.py
        mock_cost_estimator.py
        mock_token_counter.py
        mock_patient_record_integration.py
        mock_calendar_integration.py
      providers/            # Fase 5 — implementaciones reales (no Mock*)
        assemblyai_transcription_provider.py  # AssemblyAITranscriptionProvider
      factory.py             # build_transcription_provider(settings, name=None) —
                              # único punto que resuelve TRANSCRIPTION_PROVIDER
                              # por configuración (DI), ver development-plan.md
                              # Fase 5 y transcription-benchmark.md
    core/
      config.py           # settings desde variables de entorno
      db.py                 # Base declarativa + engine/session SQLAlchemy
      logging.py             # logging estructurado
      errors.py               # excepciones de dominio → respuestas HTTP
      exceptions.py            # NotFoundError, ConflictError, ForbiddenError, UnauthenticatedError
      pagination.py             # Page[T], parámetros de paginación compartidos
      context.py                 # middleware de request_id / correlation ID
      current_user.py             # CurrentUser, CurrentUserProvider, FakeCurrentUserProvider
      authorization.py             # matriz de permisos centralizada (ver §9)
      deps.py                       # dependencias FastAPI (sesión, current_user, servicios)
      processing_status.py  # ProcessingStatus compartido + transiciones válidas
      messages/
        es.py                # textos, etiquetas y prompts centralizados (i18n-ready)
    main.py
  tests/
  alembic/
```

`AudioStorage` (`audio/`) y `PromptRenderer`/`PipelineOrchestrator`
(`ai_pipeline/`) son interfaces igual de "abstractas obligatorias" que las
de `integrations/`, pero se definen dentro de su propio módulo porque no
son integraciones con sistemas externos de terceros — son puntos de
extensión internos del dominio. `integrations/` queda reservado a las
ocho interfaces e implementaciones mock del AI Pipeline
(`TranscriptionProvider`, `LanguageModelProvider`, `SummaryGenerator`,
`ClinicalFlagsGenerator`, `MissingInformationGenerator`,
`AnamnesisGenerator`, `CostEstimator`, `TokenCounter` — ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §6) más
`PatientRecordIntegration`/`CalendarIntegration` (historia clínica,
calendario) y el exportador de documentos.

**Nota sobre `ClinicalFlagRuleset` (nombre obsoleto).** El diseño previo
a la Fase 4 definía una interfaz `ClinicalFlagRuleset` dentro de
`clinical_flags/domain/`. Queda **eliminada**: su propósito lo cumple
ahora `ClinicalFlagsGenerator` (`integrations/domain/`), con la misma
implementación de referencia basada en reglas (`MockClinicalFlagsGenerator`,
heredera de `DemoClinicalFlagRuleset`) y las mismas salvaguardas clínicas
de [clinical-safety.md](clinical-safety.md) §7 — solo cambia dónde vive
la interfaz (ahora junto al resto de proveedores del pipeline, no
aislada en su propio módulo) y su firma (ya no recibe un borrador de
anamnesis, que en el nuevo orden del pipeline todavía no existe cuando
se detectan señales de alerta — ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §1.4 y §12,
decisión 18).

**Corrección sobre `RetentionCleanupService` (planificado como `Protocol` en
`audio/domain/retention.py`, nunca implementado así).** El diseño previo a la
Fase 7.2 preveía esta interfaz dentro de `audio/domain/`, con un método
`purge(audio_recording_id) -> None` (un audio por llamada) pensado para un
futuro proveedor real intercambiable. Al implementar la Fase 7.2 (ver
[development-plan.md](development-plan.md) Fase 7, hito 7.2), ese diseño
resultó innecesario: no existe ningún proveedor real que intercambiar (a
diferencia de `AudioStorage`/`TranscriptionProvider`), así que un `Protocol`
solo añadiría indirección sin beneficio. `RetentionCleanupService` se
implementó en su lugar como **clase concreta** en `app/retention/service.py`
(módulo propio, no dentro de `audio/domain/`), con purga **en bloque** de
todos los audios expirados en una sola llamada (`purge(current_user,
request_id) -> list[AudioRecording]`) en vez de uno por uno — purgar de uno
en uno habría exigido N llamadas HTTP desde el frontend sin ninguna ventaja
real. Mismo criterio que la sustitución de `ClinicalFlagRuleset` por
`ClinicalFlagsGenerator` (nota anterior): un diseño previo documentado antes
de implementarse se corrige aquí para reflejar la decisión realmente tomada,
no la prevista.

## 3. Módulos de dominio

| Módulo | Responsabilidad |
|---|---|
| `clinics` | Entidad `Clinic` mínima; sistema multi-clínica desde el modelo, sin gestión completa desde el frontend en el MVP (Fase 2). |
| `users` | Usuarios internos (`admin`/`audiologist`/`viewer`) por clínica. Sin autenticación real: solo resolución vía `CurrentUserProvider` (Fase 2). |
| `patients` | Identidad y datos administrativos mínimos del paciente (ficticio), aislados por clínica. No contiene contenido clínico. |
| `clinical_sessions` | Entidad central de la consulta: pertenece a una clínica, un paciente y un profesional responsable. Máquina de estados propia (`ClinicalSessionStatus`, Fase 3, diseño en [data-model.md](data-model.md) §8), borrado lógico (`is_archived`) independiente del estado. Base sobre la que cuelgan audio y el AI Pipeline. |
| `audio` | Subida, validación (tamaño/duración/extensión/MIME) y almacenamiento de la grabación vía `AudioStorage`; borrado físico manual bajo demanda (`DELETE /audio-recordings/{id}`, Fase 5) o por política de retención (`RetentionCleanupService`, `app/retention/`, Fase 7.2 — ver nota arriba). |
| `ai_pipeline` | Orquesta la generación de artefactos de IA (transcripción, resumen, señales de alerta, información ausente, anamnesis) a partir de un grafo de dependencias (Fase 4, diseño cerrado en [ai-pipeline-architecture.md](ai-pipeline-architecture.md)); versionado, revisión humana y aprobación mediante la entidad genérica `AIArtifact`/`AIArtifactVersion`; auditoría técnica (proveedor, modelo, coste, tiempo) en `AIGenerationRun`. |
| `clinical_flags` | Disposición humana por ítem (confirmar/descartar) sobre las señales de alerta generadas por el AI Pipeline — no genera contenido, solo gestiona su revisión individual (eje independiente de la disposición por documento de `AIArtifact`, ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §1.2). |
| `audit_log` | Registro append-only (tabla `audit_logs`) de acciones relevantes sobre pacientes, sesiones y artefactos de IA, escrito en la misma transacción que la entidad auditada. |
| `integrations` | Interfaces abstractas + mocks para proveedores externos (transcripción, modelo de lenguaje, generación de resumen/anamnesis/señales/información ausente, coste, tokens, Noah, calendario) y exportadores de documentos. |

## 4. Interfaces abstractas obligatorias

Definidas en `integrations/domain/`, implementadas en el MVP únicamente por
sus contrapartes `Mock*` — ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §6 para los
contratos completos:

- **`TranscriptionProvider`**: `transcribe(input: TranscriptionInput) -> TranscriptionResult`.
- **`LanguageModelProvider`**: interfaz de bajo nivel, `complete(prompt: RenderedPrompt, *, model=None) -> LanguageModelResponse`. Es la única interfaz que implementarían SDKs de proveedores reales; el resto de generators la componen, no la sustituyen.
- **`SummaryGenerator`**: `generate(transcript, *, context) -> SummaryDraft`.
- **`ClinicalFlagsGenerator`**: `generate(transcript, *, context) -> list[ClinicalFlagDraft]`. MVP: `MockClinicalFlagsGenerator`, checklist basado en reglas, sin `LanguageModelProvider` — no validado clínicamente (ver [clinical-safety.md](clinical-safety.md) §7).
- **`MissingInformationGenerator`**: `generate(summary, clinical_flags, *, context) -> list[MissingInfoItem]`.
- **`AnamnesisGenerator`**: `generate(transcript, missing_information, *, context) -> AnamnesisDraft`.
- **`CostEstimator`**: `estimate(*, provider, model, input_tokens, output_tokens) -> Decimal`.
- **`TokenCounter`**: `count(text, *, model) -> int`.
- **`PatientRecordIntegration`**: `sync_patient(...)`, `fetch_patient(...)` —
  sin implementación funcional real en el MVP, solo el contrato y el mock.
- **`CalendarIntegration`**: `list_upcoming_sessions(...)`,
  `create_appointment(...)` — igual que el anterior, contrato + mock.
- **`DocumentExporter`**: `export(document) -> bytes`, con implementaciones
  `PdfDocumentExporter` y `TextDocumentExporter` (estas sí reales, ya que
  exportar PDF/texto no depende de un proveedor externo de pago).

Interfaces internas del dominio, mismo nivel de obligatoriedad, definidas
junto a su módulo:

- **`AudioStorage`** (`audio/domain/`): `save(file) -> StorageReference`,
  `read(reference) -> BinaryStream`, `delete(reference) -> None`. El
  dominio de `audio` solo conoce `StorageReference` (valor opaco), nunca
  una ruta de disco ni un bucket. MVP: `LocalAudioStorage` (filesystem).
- **`PipelineOrchestrator`** (`ai_pipeline/domain/pipeline.py`):
  `run(clinical_session_id, triggered_by, steps) -> PipelineResult`. MVP:
  `SequentialPipelineOrchestrator`, síncrono, sin colas ni workers — ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §6.2.
- **`PromptRenderer`** (`ai_pipeline/domain/prompt_renderer.py`):
  `render(template, variables) -> RenderedPrompt` — ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.4.

(`ClinicalFlagRuleset`, definida aquí en el diseño previo a la Fase 4,
queda eliminada — su propósito lo cumple ahora `ClinicalFlagsGenerator`
en `integrations/domain/`, ver §2 y §4.)

Cada interfaz se selecciona en tiempo de ejecución mediante configuración
(inyección por variable de entorno / factory), nunca mediante `import`
directo del módulo consumidor a la implementación concreta.

## 5. Estados de procesamiento (`ProcessingStatus`) y máquinas de estado propias

Se define un enumerado compartido en `core/processing_status.py` con:
`uploaded`, `validating`, `ready`, `transcribing`, `transcribed`,
`failed`, `deleted`. **Aplica exclusivamente a `audio_recordings`**
(implementado en la Fase 5 — ver [data-model.md](data-model.md) §6). La
subida síncrona de esta fase no persiste el estado intermedio
`validating` como fila propia (valida antes de insertar, inserta ya en
`ready`/`failed`); las demás transiciones sí se validan y persisten
explícitamente en `AudioRecordingService`.

Las transiciones válidas (p. ej. `uploaded → validating → ready`, nunca
`uploaded → deleted` directamente) se definen y verifican en la **capa de
dominio o servicio** de cada módulo (una función/objeto `StateMachine`
por entidad), no únicamente mediante validación en el router de FastAPI.
Cualquier intento de transición inválida lanza una excepción de dominio
antes de tocar la base de datos.

Cada entidad con ciclo de vida propio tiene, en cambio, su **propia**
máquina de estados en vez de compartir `ProcessingStatus` — mismo
principio arquitectónico (transiciones validadas en dominio/servicio,
nunca solo en el router), vocabulario y reglas propias en cada caso:

- **`clinical_sessions`**: `ClinicalSessionStatus` (`scheduled`,
  `in_progress`, `completed`, `review_pending`, `reviewed`, `cancelled`),
  definida en `clinical_sessions/domain/state_machine.py` y documentada
  en [data-model.md](data-model.md) §8. Razón: el vocabulario de
  `ProcessingStatus` (pensado para un pipeline lineal de IA) no expresa
  bien el ciclo de vida real de una consulta clínica — creación directa
  en varios estados, cancelación, revisión sin IA de por medio.
- **Artefactos de IA (`ai_artifacts`/`ai_generation_runs`)**: dos ejes
  independientes, `AIGenerationRunStatus` (ejecución:
  `queued`/`processing`/`completed`/`failed`) y `AIArtifactStatus`
  (disposición humana: `review_pending`/`approved`/`rejected`),
  documentados en [data-model.md](data-model.md) §10 y
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §9.2. Razón:
  igual que `clinical_sessions`, `ProcessingStatus` mezclaría en un único
  enumerado dos conceptos distintos — si un paso técnico se ejecutó con
  éxito, y si un humano ha decidido algo sobre su resultado —. Sustituye
  al uso previsto (nunca implementado) de `ProcessingStatus` para
  `anamnesis_documents`/`session_notes`.
- **`clinical_flags`** mantiene su propio eje de estado, ya existente
  desde el diseño original: `sugerida_ia` / `confirmada_por_profesional`
  / `descartada` — disposición del profesional sobre una señal
  individual, no un estado de procesamiento ni de artefacto completo (ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §1.2).

**`ProcessingStatus` queda reservado exclusivamente a
`audio_recordings`.** Esta es una corrección acumulada respecto al diseño
original de la Fase 0/1 (que trataba `clinical_sessions` como un
agregado de `ProcessingStatus`, corregido en la Fase 3) y respecto al
diseño previo a la Fase 4 (que reservaba `ProcessingStatus` también para
`anamnesis_documents`/`session_notes`, tablas ya eliminadas — ver nota en
[data-model.md](data-model.md) §6).

## 6. Flujo end-to-end (secuencia principal)

1. El profesional crea un paciente ficticio.
2. Crea una `ClinicalSession` asociada a ese paciente.
3. Sube un audio → `audio` valida tamaño/duración/extensión/MIME
   (`uploaded` → `validating` → `ready`, o `failed` si no pasa la
   validación) y lo almacena vía `AudioStorage`.
4. El profesional dispara el AI Pipeline
   (`POST .../ai/generate`) → `ai_pipeline` ejecuta el grafo de
   dependencias completo (`Transcription` → `{Summary, Clinical Flags}` →
   `Missing Information` → `Structured Anamnesis`, ver
   [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §1.4),
   creando o versionando un `AIArtifact` por cada paso que complete con
   éxito (`AIGenerationRunStatus`: `queued` → `processing` → `completed`
   o `failed`, por paso). Cada artefacto nace en `AIArtifactStatus =
   review_pending`.
5. El profesional revisa/edita cada artefacto → cada guardado crea una
   nueva `AIArtifactVersion`; el artefacto permanece o vuelve a
   `review_pending` hasta la aprobación explícita. Para `clinical_flags`,
   además, cada ítem generado se confirma o descarta individualmente
   (tabla `clinical_flags`, disposición por ítem).
6. El profesional aprueba explícitamente cada artefacto → estado
   `approved`, se registra usuario y timestamp. Solo entonces puede
   exportarse. Una nueva edición tras la aprobación (o tras un rechazo)
   devuelve el artefacto a `review_pending` y exige nueva decisión.
7. `audit_log` registra el disparo del pipeline y cada acción de
   disposición humana (aprobar/rechazar/editar); la auditoría técnica de
   cada paso (proveedor, modelo, coste, tiempo, plantilla usada) vive en
   `ai_generation_runs`, no en `audit_logs` — ver
   [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.6.
8. El profesional exporta artefactos aprobados vía `DocumentExporter`.
9. Pasado el periodo de retención (30 días por defecto), el audio puede
   eliminarse físicamente (`deleted`) de forma manual vía
   `RetentionCleanupService`; los artefactos de IA aprobados nunca se
   eliminan físicamente, solo mediante borrado lógico auditado.

La IA nunca escribe directamente sobre el resultado persistido: `AI →
Draft → Human Review → Approve → Persist`, nunca `AI → Database` — ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §1.1.

## 7. Frontend

Estructura por pantallas/flujo, no por tipo de componente:

```
frontend/
  src/
    features/
      patients/
      sessions/
      audio-upload/
      ai-pipeline/       # disparo del pipeline, revisión/aprobación por
                          # artefacto (transcripción, resumen, anamnesis,
                          # información ausente), historial de versiones
      clinical-flags/     # disposición por ítem, dentro del artefacto de señales
      audit-log/
    shared/
      api-client/
      ui/
      auth/
      i18n/
        es.ts        # textos y etiquetas centralizados (i18n-ready)
    app/
```

El cliente API se genera/mantiene tipado contra los esquemas Pydantic del
backend (a decidir en Fase 2 si se genera OpenAPI → tipos TS o se tipa a
mano; ver [development-plan.md](development-plan.md)).

## 8. Internacionalización preparada, no implementada

El MVP es exclusivamente en español, pero ningún texto de usuario ni
prompt de IA se escribe embebido donde se usa:

- **Backend**: los avisos obligatorios de IA y el disclaimer del checklist
  de señales de alerta viven en `core/messages/es.py` como constantes con
  clave semántica (p. ej. `AI_DISCLAIMER`, `CLINICAL_FLAGS_DEMO_NOTICE`),
  nunca como literales repetidos en el código de dominio. Los
  **prompts** de los `*Generator` del AI Pipeline siguen el mismo
  principio de "nunca hardcodeados" pero con un mecanismo propio —
  plantillas versionadas en `ai_pipeline/prompts/` (git) sembradas en la
  tabla `prompt_templates` (base de datos, fuente de verdad en
  ejecución) — ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.4, no en
  `core/messages/es.py`.
- **Frontend**: mismo principio en `shared/i18n/es.ts` — componentes
  importan claves, no escriben cadenas de texto directamente.

Esto no introduce selección de idioma en tiempo de ejecución (fuera de
alcance del MVP, ver [product-requirements.md](product-requirements.md)),
solo evita que una futura internacionalización requiera reescribir código
de dominio o de UI.

## 9. `CurrentUserProvider` y autorización centralizada (Fase 2)

Sin autenticación real todavía. `CurrentUserProvider` es el puerto que
resuelve "quién hace esta petición":

```python
class CurrentUserProvider(Protocol):
    async def get_current_user(self, request: Request, session: AsyncSession) -> CurrentUser: ...
```

MVP: única implementación `FakeCurrentUserProvider` (`core/current_user.py`).
Lee un identificador de usuario de la cabecera de desarrollo
`X-Dev-User-Id` (o, si no está presente, de `DEV_DEFAULT_USER_ID` en la
configuración) y **lo resuelve contra la tabla `users`** — nunca construye
un `CurrentUser` a partir de datos enviados por el cliente sin
verificarlos en base de datos. Si el usuario no existe o está inactivo,
la petición se rechaza como no autenticada (401).

**Bloqueo en producción**: `FakeCurrentUserProvider` lanza `RuntimeError`
en su propio constructor si `settings.is_production` es verdadero. La
fábrica que construye el proveedor (`core/deps.py`) se invoca de forma
eager en el arranque de la aplicación (`lifespan`), de modo que un
despliegue mal configurado con `ENVIRONMENT=production` falla al arrancar,
no en la primera petición de un usuario real. Mientras no exista un
proveedor real, **la API no puede ejecutarse en producción** — es la
consecuencia deliberada de no implementar autenticación real todavía.

**Autorización centralizada**: `core/authorization.py` define, por
recurso, una matriz `{Role: {Action, ...}}` y una función
`authorize_<recurso>_action(current_user, action)` que la consulta. Cada
método de cada `*Service` llama a esta función como primer paso; ningún
router ni repositorio implementa comprobaciones de rol propias. Esto
evita el riesgo de "comprobaciones de permisos dispersas" — toda la
lógica de quién puede hacer qué vive en un único módulo, fácil de auditar
y de testear de forma aislada. Ver matriz completa de `patients` en
[api-specification.md](api-specification.md) §Autorización.

**Autorización con propiedad del recurso (Fase 3):** `patients` solo
necesitaba `{Role: {Action}}`. `clinical_sessions` añade una segunda
dimensión: un `audiologist` únicamente puede operar sobre sesiones donde
`professional_id == current_user.id` ("sus propias sesiones"). Se
resuelve en la misma función centralizada, no con comprobaciones nuevas
dispersas: `authorize_clinical_session_action(current_user, action,
session=None)` consulta primero la matriz de rol y, si el rol es
`audiologist` y la acción lo requiere, comprueba además la propiedad
sobre `session` (parámetro obligatorio salvo para `CREATE`/`READ` en
listado). Matriz completa en
[api-specification.md](api-specification.md) §Clinical sessions.

## 10. Aislamiento multi-clínica

Ninguna consulta de lectura o escritura puede aceptar un `clinic_id`
enviado por el cliente: siempre se deriva de `current_user.clinic_id`,
resuelto por `CurrentUserProvider` contra la base de datos. Los
repositorios exponen únicamente operaciones que exigen `clinic_id` como
parámetro obligatorio (p. ej. `get_by_id(session, clinic_id, entity_id)`),
de modo que es estructuralmente imposible consultar una entidad sin
acotar por clínica.

**Un UUID de otra clínica se trata como recurso inexistente (404), nunca
como acceso prohibido (403)**: la consulta `WHERE id = :id AND clinic_id =
:clinic_id` devuelve `None` tanto si el recurso no existe como si
pertenece a otra clínica, y el servicio traduce ambos casos al mismo
`NotFoundError`. Esto evita que la aplicación revele, ni siquiera
indirectamente mediante un código de error distinto, la existencia de
datos de otra clínica.

## 11. Decisiones de arquitectura y por qué

- **Interfaces abstractas para todo proveedor externo**: requisito
  explícito del producto y salvaguarda para no acoplar el dominio clínico a
  un proveedor de pago concreto antes de validar el flujo.
- **Separación domain/infrastructure/presentation** por módulo, en lugar de
  una arquitectura hexagonal global de una sola pieza: mantiene cada
  módulo clínico (`ai_pipeline`, `clinical_flags`, etc.) independiente y
  más fácil de razonar/testear de forma aislada.
- **Versionado explícito de artefactos de IA** (`AIArtifactVersion`, no
  solo `updated_at`): requisito de negocio (guardar original IA + versión
  final editada, poder regenerar sin perder la anterior) y de auditoría
  clínica — ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §3.3.
- **Identidad del paciente separada del contenido clínico** (módulo
  `patients` vs. resto de módulos clínicos que solo referencian
  `patient_id`): principio de privacidad desde el diseño, ver
  [privacy-and-security.md](privacy-and-security.md) y
  [data-model.md](data-model.md).
- **Un único backend modular (monolito modular)** en vez de microservicios:
  el MVP no tiene el volumen ni el equipo que justifique la complejidad
  operativa de microservicios; los límites de módulo ya preparan una
  futura extracción si hiciera falta.
- **`AudioStorage`, `PipelineOrchestrator` y `PromptRenderer` como
  interfaces internas del módulo, no en `integrations/`**: no son
  integraciones con sistemas externos de terceros sino puntos de
  extensión propios del dominio (almacenamiento físico, orquestación,
  renderizado de plantillas). Mezclarlas con `integrations/` diluiría el
  propósito de ese módulo (reservado a proveedores externos sustituibles:
  Noah, calendario, transcripción, modelo de lenguaje y los generators
  del AI Pipeline).
- **Cada entidad con ciclo de vida propio tiene su propia máquina de
  estados**, en vez de forzar un único `ProcessingStatus` compartido para
  todo: `clinical_sessions` (`ClinicalSessionStatus`), los artefactos de
  IA (`AIGenerationRunStatus`/`AIArtifactStatus`, dos ejes) y
  `audio_recordings` (`ProcessingStatus`, el único caso que realmente
  encaja con ese vocabulario). El principio que sí se comparte —
  transiciones validadas en dominio/servicio, nunca solo en el router —
  no exige compartir el vocabulario; forzarlo llevó a dos correcciones de
  diseño sucesivas (Fase 3 para `clinical_sessions`, Fase 4 para los
  artefactos de IA) documentadas en
  [data-model.md](data-model.md) §6.
- **`CurrentUserProvider` como puerto, no como parámetro implícito**: aísla
  todo el código de negocio de cómo se resuelve la identidad. La Fase 2
  usa una implementación simulada; sustituirla por autenticación real más
  adelante no debería tocar ningún `*Service` ni router, solo la
  implementación concreta inyectada.
- **Filtrado por clínica en la firma de los repositorios, no como
  comprobación aparte**: hacer `clinic_id` un parámetro obligatorio de
  cada método de repositorio (en vez de confiar en que cada servicio
  "recuerde" añadir el filtro) hace estructuralmente difícil introducir
  una fuga de datos entre clínicas por un descuido puntual.
- **Endpoints explícitos de transición para `clinical_sessions`, no un
  endpoint genérico `PATCH .../status`**: un endpoint genérico requeriría
  reimplementar dentro del cuerpo de la petición la propia matriz de
  transiciones y de permisos (¿quién puede pasar de qué a qué?), perdiendo
  la ventaja de que cada acción de negocio (`start`, `complete`,
  `submit-review`, `review`, `cancel`) tenga su propia entrada en la
  matriz de autorización, su propio nombre en la API, y su propia semántica
  de idempotencia. Los endpoints explícitos cuestan más superficie de API
  pero dan claridad, trazabilidad y permisos explícitos — priorizados
  sobre ellos según lo pedido para esta fase.
- **`ClinicalSessionStatus` separado de `ProcessingStatus`**: forzar todas
  las entidades con ciclo de vida a compartir un único enumerado genérico
  habría acoplado el diseño de `clinical_sessions` a un vocabulario
  pensado para pipelines de IA. Cada máquina de estados vive en el dominio
  del módulo al que pertenece; lo que se comparte es el **principio**
  (transiciones validadas en dominio/servicio, nunca solo en el router),
  no el vocabulario.
- **`AIArtifact`/`AIArtifactVersion` genéricos, en vez de una tabla por
  tipo de artefacto (Fase 4)**: un único mecanismo de versionado, estado
  de revisión y auditoría técnica reutilizado por los cinco artefactos
  actuales (transcripción, resumen, señales de alerta, información
  ausente, anamnesis) y por cualquier artefacto futuro, sin migración de
  esquema nueva cada vez. Análisis completo de ventajas/inconvenientes
  frente al diseño anterior (tablas independientes) en
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §3.1.
- **Contrato interno del AI Pipeline siempre en JSON estructurado, nunca
  texto libre ni Markdown**: permite validar la forma de cada tipo de
  artefacto en la capa de servicio, generar cualquier vista/documento a
  partir de la misma fuente estructurada, y evita que la salida de un
  proveedor concreto se filtre sin normalizar hacia el contenido
  persistido. Ver [ai-pipeline-architecture.md](ai-pipeline-architecture.md)
  §7.1.
- **Cada `*Generator` del AI Pipeline compone `LanguageModelProvider` en
  vez de implementarse directamente contra un SDK de proveedor** (salvo
  `ClinicalFlagsGenerator`, deliberadamente basado en reglas): separa el
  eje de "qué proveedor" del eje de "cómo se valida la salida de cada
  artefacto", de modo que cambiar de proveedor no obligue a reimplementar
  la lógica de negocio de cada artefacto. Ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.2.
