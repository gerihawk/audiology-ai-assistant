# Plan de desarrollo — Audiology AI Assistant

Fases pequeñas y verificables. Cada fase termina en un estado
funcionalmente probable de commitear (build verde, tests pasando) antes de
pasar a la siguiente. No se empieza una fase sin que la anterior esté
completa y coherente con la documentación.

## Fase 0 — Documentación fundacional (completada)

**Entregable**: README.md, CLAUDE.md y los documentos en `docs/`,
coherentes entre sí, incluidas las decisiones cerradas el 2026-08-05 (ver
[product-requirements.md](product-requirements.md) §8-9).
**Criterio de aceptación**: cumplido — el usuario validó el alcance, la
arquitectura y cerró todas las preguntas abiertas antes de arrancar la
Fase 1.

## Fase 1 — Esqueleto técnico del proyecto

Alcance exacto de esta fase (nada de pacientes, sesiones, audio,
transcripción ni IA todavía — eso empieza en la Fase 2):

**Estructura general**
- Monorepositorio: `backend/`, `frontend/`, `docs/` (ya existente),
  `infra/` (para artefactos de infraestructura local que no encajen en
  `docker-compose.yml` raíz).
- `.gitignore`, `.editorconfig`, `.env.example` en la raíz. Ningún secreto
  real versionado.
- README.md actualizado con instrucciones reales de instalación/ejecución.

**Backend**
- Python 3.12, FastAPI, `core/config.py` con Pydantic Settings (lee de
  variables de entorno, sin defaults inseguros para entornos no locales).
- SQLAlchemy 2 configurado (`core/db.py`); Alembic inicializado y listo
  para generar migraciones (sin modelos de dominio todavía: `patients` y
  el resto llegan en la Fase 2).
- Estructura de carpetas coherente con [architecture.md](architecture.md)
  §2 (`app/core/`, módulos vacíos o ausentes hasta que tengan contenido
  real — no se crean paquetes vacíos "por si acaso").
- `GET /health`: liveness, sin dependencias externas.
- `GET /ready`: comprueba conexión real a PostgreSQL.
- Manejo global de errores (exception handlers FastAPI) con respuesta JSON
  estructurada y consistente.
- Logging estructurado (JSON) que **nunca** registra cuerpos de petición
  ni datos clínicos.
- Ruff + Black configurados; Pytest con tests de `/health` y `/ready`.

**Frontend**
- React + TypeScript + Vite, ESLint + Prettier.
- Página mínima: nombre provisional del producto, estado del frontend,
  resultado de consultar `/health` (con estado de carga y de error de
  conexión visibles).
- Sin navegación clínica, formularios ni diseño definitivo todavía.

**Infraestructura local**
- `docker-compose.yml`: `db` (PostgreSQL), `backend`, `frontend`.
- Healthchecks razonables en los tres servicios.
- Volumen persistente para PostgreSQL, red interna dedicada.
- Todas las variables usadas documentadas en `.env.example`.
- Comandos sencillos (Makefile) para levantar, parar, migrar y testear.

**Seguridad básica**
- CORS restrictivo basado en variable de entorno (lista blanca de
  orígenes); nunca `*` fuera de desarrollo local.
- No se registran cuerpos de petición en logs.
- Sin credenciales por defecto inseguras para entornos distintos de local
  (local puede tener valores de ejemplo evidentes, p. ej.
  `CHANGE_ME_LOCAL_ONLY`).
- Configuración claramente separada por entorno (`development`, `test`,
  `production`) vía `ENVIRONMENT` + Pydantic Settings.

**Criterios de aceptación** (los 10 deben cumplirse):
1. `docker compose up --build` levanta los tres servicios.
2. PostgreSQL está disponible (healthcheck en verde).
3. `/health` responde correctamente.
4. `/ready` confirma conectividad real con la base de datos.
5. El frontend consulta `/health` y muestra su estado (ok/cargando/error).
6. Los tests del backend pasan.
7. Lint y formateo pasan en backend y frontend.
8. El README permite reproducir el entorno desde cero.
9. No existe ninguna integración con servicios externos.
10. No se han usado datos reales en ningún punto.

Nada de lo anterior incluye `patients`, `clinical_sessions`, `audio`,
`ai_pipeline`, `clinical_flags` ni ningún proveedor mock funcional — esos
módulos quedan vacíos de lógica de negocio
hasta la Fase 2 en adelante.

## Fase 2 — `clinics`, `users`, `patients`, `audit_log` (completada)

Objetivo: validar el patrón arquitectónico completo (dominio →
persistencia → migraciones → repositorio → servicio → autorización → API
→ auditoría → frontend → tests) con un primer módulo funcional real,
**sin** autenticación real y **sin** ninguna entidad clínica todavía.
Decisiones cerradas en [product-requirements.md](product-requirements.md)
§10.

- `clinics`, `users`, `audit_log`: dominio + ORM + repositorio mínimo, sin
  API propia (soportan `patients` y el seed).
- `patients`: dominio, ORM, repositorio, `PatientService` (autoriza →
  opera → audita → commit transaccional), esquemas Pydantic separados del
  ORM, router `/api/v1/patients` con los 6 endpoints mínimos + `/me` +
  `/dev/users`.
- `core`: excepciones de dominio → HTTP, paginación, `request_id` por
  middleware, `CurrentUser`/`CurrentUserProvider`/`FakeCurrentUserProvider`,
  `authorization.py` centralizado.
- Una migración Alembic para `clinics`/`users`/`patients`/`audit_logs` con
  sus índices.
- Script de seed idempotente (clínica + 3 usuarios + pacientes
  ficticios), bloqueado en producción.
- Frontend: selector de usuario ficticio activo, listado con
  búsqueda/paginación/filtro de archivados, crear/editar, detalle,
  archivar/restaurar.
- Tests backend (aislamiento por clínica, permisos por rol, auditoría
  transaccional, bloqueo del proveedor fake en producción) y tests
  frontend (Vitest + Testing Library).

**Criterios de aceptación**:
1. Las migraciones se ejecutan correctamente desde una base vacía.
2. El seed ficticio es reproducible (idempotente).
3. Los 8 endpoints (`patients` × 6 + `/me` + `/dev/users`) funcionan y
   están documentados en [api-specification.md](api-specification.md).
4. El aislamiento por clínica está cubierto por tests (UUID de otra
   clínica → 404).
5. Los tres roles (`admin`/`audiologist`/`viewer`) respetan la matriz de
   permisos documentada.
6. La auditoría (`patient.created/updated/archived/restored`) se genera
   de forma transaccional junto con la entidad.
7. No se registran valores sensibles en auditoría ni en logs (solo
   nombres de campos modificados).
8. El frontend permite probar el ciclo completo del paciente ficticio
   (crear, buscar, editar, archivar, restaurar) cambiando de usuario
   ficticio activo.
9. Tests, lint, format y build pasan en backend y frontend.
10. `docker compose up --build` sigue levantando los tres servicios.
11. No se implementa nada de `clinical_sessions`, `audio`, `ai_pipeline`,
    `clinical_flags`, integraciones ni autenticación real.
12. No se usan datos reales en ningún punto (seed y tests, exclusivamente
    ficticios).

## Fase 3 — `clinical_sessions` (diseño cerrado, backend en implementación)

**Cambio respecto al plan anterior**: esta fase estaba fusionada con
`audio`. Se separan: `clinical_sessions` es ahora una fase propia,
centrada exclusivamente en la sesión clínica como entidad administrativa;
`audio` pasa a ser la Fase 4. El resto de fases se renumeran en cascada
(antigua Fase 4 → 5, … antigua Fase 9 → 10).

**Diseño cerrado el 2026-08-05, decisiones finales cerradas el mismo día**
— modelo de dominio, máquina de estados (`ClinicalSessionStatus`),
matriz de permisos, modelo de datos (incluidas las columnas
`reviewed_by`/`reviewed_at`), índices, endpoints y auditoría
documentados en [data-model.md](data-model.md) §8-9,
[api-specification.md](api-specification.md) §Clinical sessions,
[architecture.md](architecture.md) §5 y §9, y
[privacy-and-security.md](privacy-and-security.md) §5-6. Todas las
decisiones cerradas en [product-requirements.md](product-requirements.md)
§11 — sin preguntas abiertas pendientes.

**Alcance de esta ronda de implementación: solo backend.** El frontend de
`clinical_sessions` queda para una ronda posterior (no se implementa
todavía).

Alcance de la **implementación de backend** de esta fase:

- `clinical_sessions/domain/`: entidad `ClinicalSession`, enums
  `SessionType`/`ClinicalSessionStatus`, `state_machine.py` con las
  transiciones válidas de §8.
- `clinical_sessions/infrastructure/`: `ClinicalSessionORM`,
  `SqlAlchemyClinicalSessionRepository`.
- `clinical_sessions/service.py`: `ClinicalSessionService` — autoriza
  (incluida la comprobación de propiedad para `audiologist`) → valida la
  transición vía `state_machine.py` → opera → audita → commit
  transaccional. Valida también, en creación, que el paciente no esté
  archivado y que el profesional pertenezca a la clínica, esté activo y
  tenga rol `admin`/`audiologist`.
- `clinical_sessions/api/`: esquemas Pydantic (`ClinicalSessionCreateRequest`,
  `ClinicalSessionUpdateRequest`, `ClinicalSessionResponse`) separados del
  ORM, router con los 11 endpoints de
  [api-specification.md](api-specification.md) §Clinical sessions.
- `core/authorization.py`: `ClinicalSessionAction` +
  `authorize_clinical_session_action` (matriz por rol + comprobación de
  propiedad).
- Migración Alembic para `clinical_sessions` con los índices de
  [data-model.md](data-model.md) §9.
- Extensión del seed: 2-3 sesiones ficticias de ejemplo en distintos
  estados, repartidas entre el admin y el audiologist ficticios.
- Tests backend: creación directa en cada estado inicial válido y
  rechazo en cada estado inválido, cada transición (válida, no-op
  idempotente sin duplicar auditoría, conflicto), conservación de
  timestamps en reintentos, ventana de edición por estado (incluida la
  restricción de `review_pending` a solo `title`/`administrative_notes`),
  matriz de permisos por rol **incluida la comprobación de propiedad**,
  aislamiento entre clínicas (404, no 403) validado en servicio,
  bloqueo de archivado desde `review_pending` y permiso desde
  `completed`/`reviewed`/`cancelled`, asignación correcta de
  `reviewed_by`/`reviewed_at` y su rechazo si los envía el cliente,
  restauración conservando el estado previo, auditoría transaccional de
  cada acción (incluido `professional_changed` con UUIDs, nunca valores
  sensibles), rollback ante fallo transaccional.
- **Frontend de `clinical_sessions`: fuera de esta ronda** (listado con
  filtros, creación, edición, detalle con transiciones explícitas,
  sesiones en el detalle de paciente, indicador de profesional
  responsable, manejo visible de permisos — diseño ya cerrado, pendiente
  de implementar en una ronda posterior).

**Criterios de aceptación del backend**:

1. Migración desde base vacía; seed reproducible con sesiones ficticias.
2. Los 11 endpoints funcionan y coinciden exactamente con
   [api-specification.md](api-specification.md) §Clinical sessions.
3. La máquina de estados rechaza toda transición no listada en
   [data-model.md](data-model.md) §8 con `409`, incluida la validación en
   dominio/servicio (no solo en el router).
4. Un `audiologist` no puede crear, editar, transicionar, cancelar ni
   archivar una sesión de otro profesional de su misma clínica (`403`);
   sí puede leerlas.
5. Solo `admin` puede revisar (`.../review`) y restaurar (`.../restore`).
6. Aislamiento por clínica cubierto por tests: `session_id` de otra
   clínica → `404`, nunca `403`.
7. Un paciente archivado no puede recibir sesiones nuevas (`409`); un
   profesional inactivo, de otra clínica o con rol `viewer` no puede
   asignarse como `professional_id` (`404`/`409` según el caso).
8. Cambiar `professional_id` genera una entrada de auditoría
   `clinical_session.professional_changed` propia, con los UUID anterior
   y nuevo; nunca se registran valores de `title`/`administrative_notes`.
9. `reviewed_by`/`reviewed_at` los asigna exclusivamente el servidor al
   ejecutar `.../review`; enviarlos desde el cliente (creación o edición)
   se rechaza con `422`. El archivado se permite solo desde `completed`,
   `reviewed` o `cancelled` — nunca desde `review_pending`. En
   `review_pending`, `PATCH` solo admite `title`/`administrative_notes`.
10. Tests y lint (Ruff, Black) pasan en el backend; `docker compose up
    --build` sigue levantando los tres servicios.
11. No se implementa nada de `audio`, `ai_pipeline`, `clinical_flags`,
    integraciones, autenticación real ni frontend de `clinical_sessions`
    (queda para una ronda posterior).
12. No se usan datos reales en ningún punto.

## Fase 4 — AI Pipeline end-to-end (diseño cerrado el 2026-08-10)

**Diseño cerrado.** Sustituye por completo al bloque de fases que ocupaba
antes este lugar (`audio` → `transcription` → `anamnesis`/`session_notes`/
`clinical_flags` como módulos independientes con tabla propia cada uno,
más una fase separada de revisión/edición/aprobación/versionado) —
contenido eliminado de este documento, no quedan dos planes posibles.
Arquitectura completa, entidades, interfaces, contratos, secuencia y
decisiones en [ai-pipeline-architecture.md](ai-pipeline-architecture.md);
esquema de datos completo en [data-model.md](data-model.md) §2 y §10-11.
**Sin preguntas abiertas** — ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §13.

El módulo `audio` (subida, validación, almacenamiento local) se integra
en esta misma fase como su primer prerrequisito (subfase 4.1, sin cambios
respecto al diseño original) — el AI Pipeline propiamente dicho (4.2 en
adelante) no depende de que 4.1 esté implementada: sus mocks trabajan
sobre una entrada de fixture, no sobre audio real (ver
[ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.7).

Ningún proveedor real (Whisper, OpenAI, Claude API, Anthropic API,
Gemini, Ollama, Llama u otra API externa), subida de audio real por parte
del usuario final, micrófono, almacenamiento definitivo de audio ni
transcripción real en ninguna subfase — todas usan exclusivamente
implementaciones `Mock*` y datos ficticios.

### Fase 4.1 — `audio`

- Módulo `audio`: interfaz `AudioStorage` + `LocalAudioStorage`; subida
  multipart; validación de tamaño/duración/extensión/MIME
  (`AUDIO_MAX_SIZE_MB`, `AUDIO_MAX_DURATION_MINUTES`); metadatos y
  checksum en `audio_recordings` (sin blob en PostgreSQL).
- Requiere una `clinical_session` existente (Fase 3) sobre la que colgar
  el audio.
- Pantalla: subir audio desde el detalle de una sesión, con feedback de
  validación.

**Criterio de aceptación**: desde una sesión clínica se sube un audio
ficticio de prueba; el audio pasa por `uploaded → validating → ready` (o
`failed` si no cumple los límites).

### Fase 4.2 — Dominio del AI Pipeline

- `ai_pipeline/domain/`: entidades (`AIArtifact`, `AIArtifactVersion`,
  `AIGenerationRun`, `AIPipelineRun`, `PromptTemplate`, `PipelineResult`),
  enums (`AIArtifactType`, `AIArtifactStatus`, `AIGenerationRunStatus`,
  `AIPipelineRunStatus`, `AIArtifactVersionSource`) — ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §4.
- Interfaces (`Protocol`): `AIArtifactRepository`,
  `GenerationRunRepository`, `PipelineRunRepository`,
  `PromptTemplateRepository`, `PipelineOrchestrator`, `PipelineStep`,
  `PromptRenderer` — ver §6.2-6.3.
- `clinical_flags/domain/`: entidad `ClinicalFlag`, repositorio — módulo
  de disposición por ítem, sin cambios de fondo respecto al diseño
  previo, solo reubicado (ya no depende de una interfaz
  `ClinicalFlagRuleset` propia, ver §4.4).
- Tests de dominio puro: transiciones de `AIGenerationRunStatus`/
  `AIArtifactStatus`, invariantes de versionado (`version_number`
  monótono, `current_version_id` siempre apunta a la última),
  `depends_on()` de cada paso según el grafo de
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §1.4 — sin
  ninguna dependencia de SQLAlchemy, FastAPI ni ningún proveedor
  concreto.

**Criterio de aceptación**: los tests de dominio pasan de forma aislada
(el paquete `ai_pipeline/domain` es importable sin SQLAlchemy ni FastAPI
instalados).

### Fase 4.3 — Persistencia

- `ai_pipeline/infrastructure/`: ORM (`AIArtifactORM`,
  `AIArtifactVersionORM`, `AIGenerationRunORM`, `AIPipelineRunORM`,
  `PromptTemplateORM`) + repositorios SQLAlchemy.
- Migración Alembic para las 5 tablas nuevas, con los índices de
  [data-model.md](data-model.md) §11.
- Migración para `clinical_flags` (reubicación de módulo, sin cambio de
  esquema) y para `consents.consent_version` (columna nueva).

**Criterio de aceptación**: migración desde base vacía funciona; existen
todos los índices/`UNIQUE` documentados; ningún `Mock*` ni endpoint
todavía.

### Fase 4.4 — Providers Mock

- Las ocho interfaces de proveedor (`integrations/domain/`):
  `TranscriptionProvider`, `LanguageModelProvider`, `SummaryGenerator`,
  `ClinicalFlagsGenerator`, `MissingInformationGenerator`,
  `AnamnesisGenerator`, `CostEstimator`, `TokenCounter` — ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §6.1.
- Sus ocho `Mock*` (`integrations/mocks/`), deterministas, sin llamadas
  de red. `MockClinicalFlagsGenerator` es basado en reglas (checklist),
  hereda directamente la lógica de la antigua
  `DemoClinicalFlagRuleset` — no usa `MockLanguageModelProvider`.
- Fixtures de transcripción deterministas para `MockTranscriptionProvider`
  (resuelve la dependencia de audio real sin bloquear esta fase).
- Tests: determinismo (misma entrada → misma salida) de cada `Mock*`;
  ausencia de lenguaje prohibido y de asignación de `informado` sin
  evidencia en `MockAnamnesisGenerator` (reutilizando la lista de
  [clinical-safety.md](clinical-safety.md) §3).

**Criterio de aceptación**: cada `Mock*` tiene tests de determinismo y de
seguridad clínica pasando; ninguno realiza I/O de red.

### Fase 4.5 — Orquestador y servicio

- `ai_pipeline/domain/pipeline.py`: `SequentialPipelineOrchestrator`
  (síncrono, respeta el grafo de dependencias — sin colas, workers ni
  procesamiento distribuido).
- `ai_pipeline/service.py`: `AIPipelineService` — autoriza → ejecuta el
  pipeline → persiste artefactos/versiones/runs → audita → commit
  transaccional. Incluye el punto de extensión de comprobación de
  consentimiento (sin bloquear en el MVP, ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7.3).

**Criterio de aceptación**: disparar el pipeline sobre una sesión
ficticia respeta el orden del grafo; un fallo en `summary` no impide que
`clinical_flags` se ejecute (dependencias independientes); un fallo en
`missing_information` provoca que `anamnesis` se salte (`skipped`, no
`failed`); cada `ai_generation_runs` tiene
`provider_name`/`latency_ms`/`execution_time_ms`/`estimated_cost_usd`/
tokens poblados.

### Fase 4.6 — API

- `ai_pipeline/api/`: esquemas Pydantic, router con los endpoints de
  [api-specification.md](api-specification.md) §AI Pipeline.
- `clinical_flags/api/`: `PATCH /clinical-flags/{flag_id}`.
- `core/authorization.py`: `AIArtifactAction`/`AIPipelineAction` — mismo
  patrón que `ClinicalSessionAction` (matriz por rol + comprobación de
  propiedad para `audiologist`).

**Criterio de aceptación**: los endpoints responden según los contratos
de [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §7;
`403`/`404`/`409` se comportan igual que en `clinical_sessions`; un
segundo disparo del pipeline mientras hay uno en curso devuelve `409`.

### Fase 4.7 — Prompt management

- `ai_pipeline/prompts/` (git): fichero por plantilla, uno por
  `artifact_type` que la usa.
- Script de seed que puebla `prompt_templates` desde esos ficheros si no
  existe ya una versión activa con ese `name`.
- `PromptRenderer` con validación de `variables_schema`.
- Configuración `ai_store_rendered_prompts` (`core/config.py`, `false`
  por defecto).
- Tests: ausencia de lenguaje prohibido en cada plantilla; con
  `ai_store_rendered_prompts=false` las columnas de prompt renderizado
  son siempre `NULL`; regenerar tras publicar una plantilla nueva usa la
  nueva versión; ejecuciones anteriores siguen apuntando a la versión que
  realmente usaron.

**Criterio de aceptación**: existe al menos una plantilla activa por
`artifact_type` que la usa, sembrada desde git.

### Fase 4.8 — Frontend

- Pantallas: disparar el pipeline desde el detalle de una sesión; ver
  cada artefacto con su aviso de IA y su `confidence`; ver historial de
  versiones; aprobar/rechazar/editar; disposición por ítem de
  `clinical_flags`.

**Criterio de aceptación**: desde la UI se puede probar el ciclo completo
(disparar → revisar → aprobar/rechazar/editar → exportar, una vez exista
la Fase 6) con datos ficticios, sin audio real.

## Fase 5 — Audio + Benchmark de Transcripción

Ampliación explícita del alcance original del MVP — ver "Fuera de las
fases del MVP" más abajo: el diseño previo excluía cualquier proveedor de
transcripción real hasta "un nuevo ciclo de análisis de alcance"; esta
fase es ese ciclo, decidido explícitamente por el producto.

- Módulo `audio` completo: entidad `AudioRecording` (ver
  [data-model.md](data-model.md) §2), interfaz `AudioStorage` +
  `LocalAudioStorage` (ver [architecture.md](architecture.md) §4),
  validación de subida (tamaño/duración/extensión/MIME), repositorio,
  servicio (`AudioRecordingService`) y API (`audio/api/`).
- `ProcessingStatus` (`core/processing_status.py`) implementado por fin
  para `audio_recordings` — ver [data-model.md](data-model.md) §6.
- Endpoints: `POST`/`GET /clinical-sessions/{id}/audio-recordings`,
  `DELETE /audio-recordings/{id}` — varias grabaciones direccionables por
  su propio ID dentro de una misma sesión, no una única grabación por
  sesión. **Supera al diseño previo** de
  [api-specification.md](api-specification.md) §Audio (`.../audio`
  singular, con endpoint de descarga) — esa sección queda pendiente de
  actualizar; sin endpoint de descarga del binario en esta fase
  (deuda técnica explícita, ver criterio de aceptación).
- Ampliación cerrada del contrato `TranscriptionProvider` (ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §6.1/§7.1):
  `TranscriptionInput.audio` (opcional) y
  `TranscriptionResult.duration_ms`/`segments` (opcionales) — el Mock
  Pipeline (`run-mock-pipeline`) no cambia de comportamiento ni de
  `content` persistido.
- `AssemblyAITranscriptionProvider`: primer proveedor real, API REST
  oficial vía `httpx` (sin SDK de terceros), credenciales únicamente por
  variable de entorno. Selección exclusivamente por configuración
  (`TRANSCRIPTION_PROVIDER=mock|assemblyai`) resuelta por Dependency
  Injection en `app/integrations/factory.py` — añadir un proveedor nuevo
  (Deepgram, OpenAI, Speechmatics...) es añadir una entrada a ese
  registro, sin tocar el resto del sistema.
- Endpoint `POST /audio-recordings/{id}/transcribe`: genera (o versiona)
  el `AIArtifact` de tipo `transcript` a partir de un audio real y el
  proveedor configurado — ruta independiente del Mock Pipeline, que
  sigue funcionando exactamente igual; nunca toca
  Summary/ClinicalFlags/MissingInformation/Anamnesis.
- `benchmark/` (`backend/benchmark/`): plataforma independiente del AI
  Pipeline (no toca la base de datos ni crea `AIArtifact`) para ejecutar
  el mismo audio contra varios `TranscriptionProvider` y comparar
  resultados normalizados — ver
  [transcription-benchmark.md](transcription-benchmark.md).

**Criterio de aceptación**: se puede subir un audio ficticio, elegir Mock
o AssemblyAI mediante configuración, generar un `AIArtifact` de tipo
`transcript` a partir de ese audio, ejecutar `python -m benchmark.cli`
comparando proveedores y obtener un JSON de resultados por proveedor en
`benchmark/results/<provider>/<audio>.json` — sin tocar el resto del AI
Pipeline ni el Mock Pipeline existente.

**Deuda técnica explícita**: sin endpoint de descarga del binario; sin
`RetentionCleanupService` todavía (sigue siendo Fase 7, sin cambios).

### Fase 5.1 — Benchmark científico y reproducible

Amplía el benchmark de la Fase 5 (misma numeración de fase, sin
renumerar nada posterior): golden dataset (`benchmark/dataset/<id>/`,
`reference.json`/`metadata.json`), WER real (`benchmark/metrics/wer.py`),
métricas de terminología/negaciones/lateralidad/diarización específicas
de audiología, `AudioCostEstimator` real (`pricing_table`, sustituye a
`MockCostEstimator` para informar coste), trazabilidad de modelo de
AssemblyAI (`model_name`/`provider_metadata`) y `python -m benchmark.compare`.
Ver [transcription-benchmark.md](transcription-benchmark.md) para el
diseño completo — WER ya no es deuda técnica de esta fase.

### Fase 5.2 — ¿Resuelve una mejor configuración de AssemblyAI la diarización?

Antes de integrar un segundo proveedor, comprueba si el fallo de
diarización observado en la primera prueba real (`consulta_ficticia_01`,
Fase 5) se resuelve con una configuración distinta de AssemblyAI, siempre
oficialmente soportada — nunca supuesta. Dos perfiles comparables sobre
el mismo audio: `assemblyai_baseline` (idéntico a producción) y
`assemblyai_optimized` (`speech_models=["universal-3-5-pro"]`,
`speakers_expected=2`, Medical Mode, `keyterms_prompt` con un vocabulario
audiológico fijo y versionado). Ver
[transcription-benchmark.md](transcription-benchmark.md) §19 para el
diseño completo, criterio de éxito de diarización y coste por
componentes.

**Resultado:** mejora parcial pero insuficiente — `assemblyai_optimized`
sigue fusionando ~83% del diálogo en un único speaker (el texto
transcrito es idéntico entre ambos perfiles), a más del doble del coste
de `baseline`. AssemblyAI se mantiene válido para precisión textual, pero
no como líder de diarización. Decisión: evaluar Deepgram Nova-3 (Fase
5.3) antes de dar por cerrada la elección de proveedor.

### Fase 5.3 — Golden dataset + integración de Deepgram Nova-3

Dos partes independientes:

- **Golden dataset de `consulta_ficticia_01`**: cerrar `reference.json`/
  `metadata.json` reales usando exclusivamente el guion original grabado
  como fuente de verdad — nunca la transcripción de un proveedor bajo
  evaluación, para no invalidar el propio WER que se quiere medir con
  ella. **Bloqueado**: el guion original no existe en el repositorio;
  pendiente de que se aporte antes de poder generar estos ficheros y
  recalcular métricas sobre los resultados ya existentes.
- **`DeepgramTranscriptionProvider`**: segundo proveedor real, mismo
  contrato normalizado (§4 de
  [transcription-benchmark.md](transcription-benchmark.md)), endpoint
  regional EU por defecto (residencia de datos, decisión deliberada para
  un producto sanitario), perfil de benchmark `deepgram_nova3_baseline`,
  pricing propio nunca mezclado con el de AssemblyAI. Implementación,
  configuración y tests completos y en verde. **Llamada real bloqueada**:
  `DEEPGRAM_API_KEY` no está configurada en el entorno — pendiente de que
  se configure para ejecutar el baseline real y generar la comparación de
  3 vías (`assemblyai_baseline`/`assemblyai_optimized`/
  `deepgram_nova3_baseline`) con clasificación de errores
  CRÍTICO/MAYOR/MENOR. Ver
  [transcription-benchmark.md](transcription-benchmark.md) §20 para el
  diseño completo.

## Fase 6 — Exportación, documentación clínica completa e IA real

**Ampliación explícita de alcance** (equivalente a la ya declarada en
Fase 5), formalizada en [fase-6-rfc.md](fase-6-rfc.md) v2, documento
normativo para toda la Fase 6 a partir de aquí:

1. activación controlada de un proveedor LLM real;
2. guardarraíles de seguridad y grounding en runtime;
3. edición humana real y borrado lógico auditado de `AIArtifact` como
   precondiciones;
4. nuevos artefactos `PATIENT_SUMMARY` y `SESSION_NOTES`;
5. actualización explícita y acotada de anamnesis (`AnamnesisUpdateStep`);
6. vista longitudinal de solo lectura mediante `clinical_record`.

El compromiso original de exportación se mantiene íntegro:

- Interfaz `DocumentExporter` con `PdfDocumentExporter` y
  `TextDocumentExporter` — implementado (hito 6.6, `app/export/`).
- Endpoint de exportación individual
  (`GET /ai-artifacts/{artifact_id}/export?format=pdf|text`), bloqueado
  si el artefacto no está `approved`, vigente y no eliminado —
  implementado (hito 6.6).
- `clinical_record`: módulo independiente de solo lectura (sin tabla ni
  ORM propios) que agrega la historia clínica longitudinal de un
  paciente — implementado (hito 6.7, `app/clinical_record/`).
  `GET /patients/{patient_id}/clinical-record` (vista paginada) y
  `GET /patients/{patient_id}/clinical-record/export?format=pdf|text`
  (exportación longitudinal `scope=patient`, reutilizando
  `DocumentExporter`, sin exportador propio).
- Pantalla: botón de exportar (PDF/texto) y vista de historia clínica
  longitudinal — pendiente (frontend, fuera del alcance de 6.6/6.7).

**Criterio de aceptación**: un artefacto aprobado se descarga como PDF y
como texto plano con formato legible; un artefacto no aprobado devuelve
error controlado y la UI no ofrece la opción. Ver
[fase-6-rfc.md](fase-6-rfc.md) §10 para el roadmap de hitos (6.0-6.7) y
los criterios de aceptación de cada uno.

**Estado (hito 6.7.5 — cierre de Fase 6 backend)**: hitos 6.0-6.7
implementados y verificados (1112 tests backend en verde, `ruff`/`black`
limpios, migración Alembic única desde base vacía). Fase 6 backend
cerrada dentro del alcance de [fase-6-rfc.md](fase-6-rfc.md). Pendiente
explícitamente fuera de alcance: frontend de exportación e historia
clínica longitudinal, proveedor/modelo LLM de producción distinto del ya
configurado (revisable ante un benchmark posterior, ver RFC §11.2), y
toda integración externa (Noah/HIMSA, calendario) — ver Fase 7.

**Estado (cierre de Fase 6 frontend)**: implementado el pendiente
señalado arriba — routing con URLs canónicas y deep-links, disparo del
pipeline mock/real, revisión de los 7 `AIArtifactType` (incluido
`source_excerpt` visible en `anamnesis`/`clinical_flags`/`session_notes`,
nunca en `transcript`/`summary`/`patient_summary`/`missing_information`,
que no lo llevan en su `content`), historial de versiones,
aprobar/rechazar, edición humana de `summary`/`patient_summary`,
`propose-anamnesis-update`, historia clínica longitudinal y exportación
individual/longitudinal PDF/texto. Auditoría de cierre (2026-08-18)
determinó que ningún documento normativo exige editor de UI para los
otros 5 `AIArtifactType` — decisión explícita, no una omisión:

- `transcript`: edición diferida hasta decidir cómo invalidar o
  revalidar el `source_map`/`source_excerpt` de los artefactos que ya se
  generaron con grounding contra el texto anterior — editar el transcript
  hoy dejaría trazabilidad "verificada" que ya no correspondería al texto
  real, sin que nada lo detecte.
- `clinical_flags`: sin editor genérico — su disposición diseñada es por
  ítem (confirmar/descartar), no edición de contenido completo (ver
  [ai-pipeline-architecture.md](ai-pipeline-architecture.md) §1.2). Esa
  disposición por ítem sigue documentada
  (`PATCH /clinical-flags/{flag_id}` en
  [api-specification.md](api-specification.md)) pero **no existe en el
  backend actual** — ni tabla `clinical_flags` ni router ni módulo; deuda
  documental detectada en la auditoría de cierre, no corregida aquí para
  no inventar un requisito nuevo sin decidirlo aparte.
- `missing_information`: no requiere editor — son sugerencias de
  seguimiento para la próxima visita, no una afirmación clínica que
  corregir; aprobar/rechazar el artefacto completo ya cubre "revisado".
- `anamnesis`: sin editor genérico de contenido — colisionaría con
  `propose-anamnesis-update` (el mecanismo normativo ya cerrado para
  modificarla, con evidencia nueva explícita y motivo tipado) y, al
  saltarse `GroundingValidator` como toda edición humana, permitiría
  marcar un campo `informado` sin verificar el `source_excerpt` tecleado.
- `session_notes`: candidato natural para un incremento futuro (mismo
  espíritu narrativo que `summary`/`patient_summary`, sin las
  restricciones de los otros cuatro), pero no es requisito de cierre de
  esta fase.

## Fase 7 — `integrations` (Noah/calendario), `consents`, retención

- Interfaces `PatientRecordIntegration` y `CalendarIntegration` +
  `Mock*`, sin llamadas de red reales.
- Endpoints de configuración de integraciones (`GET/PATCH /integrations`).
- Endpoints y pantalla de registro de consentimiento. El modelo
  (`consents`, dominio + infraestructura + migración) y la comprobación
  bloqueante en `AIPipelineService.run_pipeline` ya existen desde la
  Fase 6 (hito 6.0, ver [fase-6-rfc.md](fase-6-rfc.md) §9.1); a esta fase
  le queda únicamente construir cómo se concede el consentimiento
  (endpoint + pantalla en la ficha de paciente), que hasta ahora no
  existía en ningún punto del código.
- Interfaz `RetentionCleanupService` (`find_expired_audio`, `purge`) y
  endpoints manuales de retención (`GET/POST /retention/expired-audio...`)
  usando `RETENTION_DAYS_DEFAULT` (30 días); sin scheduler todavía.
- Pantalla mínima de administración de integraciones y retención (solo
  lectura del estado mock + registro de consentimiento en la ficha de
  paciente + listado/purga manual de audio expirado).

**Criterio de aceptación**: el estado de integraciones es consultable y
configurable a nivel de aplicación, sin que exista código que llame a un
servicio externo real. Se puede registrar consentimiento para un paciente
y purgar manualmente audio que supere la retención configurada.

**Estado (hito 7.1 — consentimiento, cerrado)**: `ConsentService` +
`consents/api/` (`POST`/`GET /patients/{patient_id}/consents`)
implementados sobre el dominio/infraestructura ya existentes desde el
hito 6.0 — el único hueco de ese módulo era conceder consentimiento, y
queda cerrado. `ConsentAction` (`READ`/`CREATE`) en
`core/authorization.py`: solo `audiologist` registra; `admin` lee sin
poder registrar; `viewer` sin acceso — deliberadamente distinto del
patrón "admin sin restricción" del resto de matrices, porque registrar
consentimiento es un acto asistencial ante el paciente. `consent_version`
la fija siempre el servidor (`settings.ai_processing_consent_version`
para `procesamiento_ia`; `null` para los otros dos tipos, sin política
versionada todavía); un envío del cliente se rechaza con `422`, mismo
criterio que `reviewed_by`/`reviewed_at` en `clinical_sessions`.
`clinical_session_id` queda fuera de esta ronda (siempre `null`, el
dominio ya soporta el campo). Paciente archivado → `409`; otra clínica →
`404`. Histórico append-only (`ConsentRepository.list_by_patient`, nuevo)
sin índice adicional — `ix_consents_patient_type` ya cubre el filtro por
`patient_id` y el volumen por paciente no justifica un índice dedicado
para el `ORDER BY recorded_at`. Frontend: sección mínima en la ficha de
paciente (`PatientConsentsSection`), no en la de sesión — listado +
formulario de alta, visible solo para `audiologist`. `docs/api-specification.md`
corregido (`clinician` → `audiologist`, rol inexistente en el código).
**Estado (hito 7.2 — retención, cerrado)**: `RetentionCleanupService`
(`app/retention/service.py`) + `retention/api/` (`GET`/`POST
/retention/expired-audio...`) sobre la infraestructura de `audio` ya
existente desde la Fase 5 — el borrado físico manual
(`AudioRecordingService.delete()`) ya existía; a esta fase le quedaba
únicamente decidir qué audio hay que purgar y exponerlo. Decisiones
cerradas: (1) "expirado" es cualquier `audio_recordings` con
`status != deleted` y `uploaded_at` anterior a `now -
RETENTION_DAYS_DEFAULT` días (nuevo, `core/config.py`, 30 por defecto) —
incluye deliberadamente estados atascados (`failed`/`uploaded`/
`validating`/`transcribing`), no solo `ready`/`transcribed`, porque un
audio olvidado a medio subir es justo el caso que la retención debe
capturar; (2) `RetentionCleanupService` es una clase concreta sin puerto
propio (a diferencia de `AudioStorage`/`TranscriptionProvider`) — opera
sobre `AudioRecordingRepository.list_expired` (nuevo) y reutiliza
`AudioRecordingService.delete()` para el borrado real, sin duplicar esa
lógica; (3) `POST /retention/expired-audio/purge` no acepta body: siempre
recalcula `find_expired_audio` en el momento de ejecutarse, nunca una
lista de IDs enviada por el cliente; (4) la purga NO es una única
transacción atómica — cada `delete()` reutilizado hace su propio commit,
así que si un registro falla los anteriores ya purgados quedan purgados y
una purga posterior (idempotente) recoge el resto; (5) `RetentionAction`
(`READ`/`PURGE`) en `core/authorization.py`: solo `admin` tiene alguna
acción, ni siquiera `audiologist` puede leer — a diferencia del patrón de
`ConsentAction`, la purga de audio es una tarea puramente administrativa;
(6) tras purgar, además de un `audio_recording.deleted` por registro
(ya existente), se escribe una única entrada resumen
`retention.purge_executed` (`purged_count`, `audio_recording_ids`), solo
si `purged_count > 0` — así queda distinguible en `audit_log` que ese
borrado vino de la política de retención. Frontend: pantalla mínima
`/retention` (solo `admin`, `RetentionPage`/`ExpiredAudioSection`) —
listado con los mismos campos que `AudioRecordingResponse` + botón
"Purgar audio expirado" con confirmación explícita (`window.confirm`,
mismo patrón que archivar paciente/sesión), porque es un borrado físico
irreversible. Sin scheduler (Fase 8) ni retención configurable por
clínica (global vía `RETENTION_DAYS_DEFAULT`, fuera de alcance).

**Estado (hito 7.3 — integrations, cerrado)**: `integration_configs`
(entidad + enum `IntegrationName`, solo `patient_record`/`calendar` —
`transcription`/`language_model` siguen resueltos por `Settings`, ver
corrección en [data-model.md](data-model.md) §2) + `IntegrationConfigService`
+ `integrations/api/` (`GET`/`PATCH /integrations...`) en `app/integrations/`
(extiende el módulo ya existente desde las Fases 5/6.3, sin colisión con
`TranscriptionProvider`/`LanguageModelProvider`/los `*Generator`).
`IntegrationConfigAction` (`READ`/`UPDATE`) en `core/authorization.py`: solo
`admin`, ni siquiera `audiologist` — mismo patrón que `RetentionAction`,
configurar integraciones externas es una tarea puramente administrativa.
Decisiones cerradas: (1) sin `clinic_id` propio — configuración global de
aplicación, cualquier `admin` de cualquier clínica puede leer/editar,
excepción deliberada al aislamiento por clínica del resto del sistema; (2)
`PATCH .../{integration_name}` acepta `enabled`/`active_provider` (ambos
opcionales, `extra="forbid"`, al menos uno obligatorio) — `active_provider`
restringido a `Literal["mock"]`, único valor válido en el MVP; body vacío o
`active_provider` inválido → `422` nativo; `integration_name` desconocido en
la ruta → `422` (enum de FastAPI); fila no sembrada aún → `404`; sin cambios
reales → no-op idempotente, sin nueva entrada de auditoría (mismo criterio
que `patients.archive`/`restore`); (3) migración Alembic
(`f3d8b1c4a920_create_integration_configs`) + seed idempotente (extiende
`app/seed.py`, mismo patrón que el resto de entidades sembradas en ese
script — no un script CLI aparte, a diferencia de `prompt_templates`): las 2
filas (`patient_record`, `calendar`) con `active_provider="mock"`,
`enabled=False`; (4) `PatientRecordIntegration`/`CalendarIntegration`
(Protocols + DTOs propios, nunca `Patient`/`ClinicalSession` directamente)
en `integrations/domain/`, marcadas explícitamente como **provisionales**
en su docstring — firma basada en investigación ligera de alcance, no en la
API real de ningún proveedor; `MockPatientRecordIntegration`/
`MockCalendarIntegration` deterministas, sin I/O de red, sin ningún caller
real desde otro módulo (verificado con un test dedicado que escanea el
árbol de `app/` en busca de imports fuera de `integrations/`) — contrato +
mock probado, tal y como especifica la documentación del MVP.
`docs/architecture.md` corregido: `RetentionCleanupService` (Fase 7.2) ya
no se documenta como `Protocol` en `audio/domain/retention.py` (diseño
previo nunca implementado así) sino como clase concreta en
`app/retention/service.py`, con purga en bloque — mismo criterio de
corrección ya usado por este propio documento cuando la Fase 4 sustituyó
por completo al bloque de fases anterior.

**Fase 7 completa (7.1 + 7.2 + 7.3).** Las tres subfases quedan cerradas:
registro de consentimiento, retención manual de audio expirado, y
configuración (solo lectura desde el frontend) de las dos integraciones
abstractas sin proveedor real. Ningún código del MVP llama a un servicio
externo de pago — todas las integraciones externas siguen siendo `Mock*`
seleccionadas por configuración. Fase 8 (RBAC más fino, scheduler de
retención, hardening) queda como siguiente ronda, sin empezar.

## Fase 8 — RBAC más fino, scheduler de retención, hardening

- Revisión de permisos por endpoint según
  [privacy-and-security.md](privacy-and-security.md), incluida la matriz
  de `AIArtifactAction`/`AIPipelineAction` de la Fase 4.
- Automatización opcional (scheduler/cron) sobre el
  `RetentionCleanupService` ya existente desde la Fase 7 — el servicio no
  cambia, solo se añade quién lo invoca periódicamente.
- Revisión de seguridad general (dependencias, cabeceras HTTP, límites de
  tamaño de subida, rate limiting básico si el tiempo lo permite).
- Evaluar si activar en producción, por defecto, el flag
  `AI_PROCESSING_CONSENT_ENFORCED` (comprobación construida y disponible
  desde la Fase 6, hito 6.0 — ver [fase-6-rfc.md](fase-6-rfc.md) §9.1;
  esta fase decide su activación por defecto, no su existencia).

**Criterio de aceptación**: checklist de
[privacy-and-security.md](privacy-and-security.md) revisado punto por
punto contra el estado real del código, con desviaciones documentadas
explícitamente si las hay.

**Estado (hito 8.1 — auditoría RBAC, cerrado)**: los diez enums de
`core/authorization.py` (`PatientAction`, `ClinicalSessionAction`,
`AudioRecordingAction`, `AIPipelineAction`, `AIArtifactAction`,
`ClinicalDocumentAction`, `ClinicalRecordAction`, `ConsentAction`,
`RetentionAction`, `IntegrationConfigAction`) auditados endpoint por
endpoint contra los nueve routers reales y sus repositorios SQLAlchemy —
detalle completo, con los cuatro invariantes verificados, en
[privacy-and-security.md](privacy-and-security.md) §13 (nueva). Único
hallazgo estructural: `ClinicalSessionService.create()` comprobaba
propiedad del profesional asignado con un `if current_user.role ==
Role.AUDIOLOGIST` manual en vez de vía `authorize_clinical_session_action()`
— única excepción en todo el backend al invariante "todo pasa por
`authorize_*`"; comportamiento observable ya correcto (no era una fuga),
pero autorización descentralizada. Corregido centralizando la comprobación
en `authorize_clinical_session_action()` (`CREATE` añadido a
`_OWNERSHIP_REQUIRED_ACTIONS`, mismo mecanismo que `CHANGE_PROFESSIONAL`),
con test dedicado nuevo
(`tests/test_clinical_session_authorization.py`, 4 casos). Suite completa
(1186 tests) en verde, lint/format limpios. Deuda consciente documentada
sin corregir: `AIPipelineAction.READ` declarado pero sin ningún endpoint
que lo invoque (permiso vestigial, sin riesgo); la excepción de
aislamiento por clínica de `integration_configs` (Fase 7.3) confirmada
como la única existente. Matriz `AIArtifactAction`/`AIPipelineAction` de
la Fase 4 (la más antigua) verificada coherente con
`ai_pipeline/api/router.py`: los cinco/dos miembros de cada enum se usan
todos salvo el `READ` de `AIPipelineAction` ya señalado. Hito 8.4
(hardening general) queda para la siguiente ronda, sin empezar.

**Estado (hito 8.2 — automatización de `RetentionCleanupService`,
cerrado)**: comando de gestión `app/retention/cli.py`
(`python -m app.retention.cli`, target `make retention-purge`) — mismo
patrón de bootstrap que `app.seed` (`app.core.orm_registry`,
`get_session_factory()`), pero sin el guard que bloquea `app.seed` en
`ENVIRONMENT=production`: este comando debe poder ejecutarse justo ahí.
Deliberadamente **sin scheduler en proceso** (nada de APScheduler ni
hilos de fondo) — es una invocación única por ejecución, pensada para que
un cron externo (host o sidecar de docker-compose) la programe
periódicamente; `RetentionCleanupService.purge()` no cambia, sigue
exigiendo un `CurrentUser` admin y opera por clínica. Como no hay
petición HTTP de la que resolver ese `CurrentUser`, el comando recorre
todos los usuarios (`UserRepository.list_all()`), agrupa por `clinic_id` y
purga cada clínica actuando como su primer admin activo, en orden
determinista por `created_at` — lógica extraída a
`_resolve_admin_per_clinic()`, función pura testeable sin base de datos.
Una clínica sin ningún admin activo se omite y se registra en stdout
(`[omitida] clínica <id>: sin admin activo`), sin abortar la purga de las
demás — una clínica mal configurada no debe bloquear al resto. Una sesión
por clínica (nunca se reutiliza la misma sesión entre clínicas), con un
`request_id` (`uuid4`) nuevo por invocación. Único cambio no funcional
sobre el diseño original: `main()` acepta un `session_factory` inyectable
(por defecto `None` → `get_session_factory()` de `app.core.db`,
idéntico al uso real por cron) para que el test de integración pueda
apuntarlo a la base de datos de test aislada en vez de a la de
desarrollo. Tests: unitarios de `_resolve_admin_per_clinic` (primer admin
activo gana, clínica sin admin se omite) + uno de integración end-to-end
en `tests/test_retention_cli.py` que crea una clínica con admin y un
audio expirado, invoca `main()` de verdad y comprueba tanto el borrado
físico (`status=deleted`) como la entrada de auditoría
`retention.purge_executed` con el `audio_recording_id` correspondiente —
mismo patrón de aserciones que `test_retention_api.py` (hito 7.2). Suite
completa (1189 tests) en verde, ruff/black limpios.

**Estado (hito 8.3 — decisión sobre `AI_PROCESSING_CONSENT_ENFORCED`,
cerrado)**: evaluado si forzar el flag a `true` incondicionalmente en
producción (punto 4 de esta fase). **Decisión: se mantiene tal cual, sin
forzarlo** — motivo y condición de revisión futura documentados en
[privacy-and-security.md](privacy-and-security.md) §7. Resumen: el
validador de `Settings` (`core/config.py`) ya exige
`ai_processing_consent_enforced=true` en production en el único
escenario relevante — al menos un `artifact_type` con proveedor LLM real
activo; con los tres `artifact_type` de `run_pipeline` todavía en
`mock`, forzarlo incondicionalmente no reduce ningún riesgo adicional y
solo añade fricción a development/test. Se revisa cuando se active de
verdad un proveedor LLM real en producción, no antes. Decisión revisada
y cerrada, no una omisión. Ronda puramente documental: sin cambios de
código, sin cambios de tests, suite completa sigue en el mismo estado
verde del hito 8.2.

**Estado (hito 8.4 — revisión de seguridad general, cerrado, aplazado)**:
evaluado el punto 3 de esta fase (cabeceras HTTP, rate limiting básico,
revisión de límites de subida). **Decisión: se aplaza por completo**,
documentado como deuda consciente en
[privacy-and-security.md](privacy-and-security.md) §11 (nueva entrada de
la tabla de amenazas) — el propio plan ya marcaba este punto como
opcional ("si el tiempo lo permite"). Estado real verificado en
`app/main.py`: exactamente tres middlewares montados hoy
(`CORSMiddleware`, `RequestIdMiddleware`, `log_requests`); ningún
middleware de cabeceras de seguridad (`X-Content-Type-Options`,
`X-Frame-Options`, etc.) ni de rate limiting. Motivo del aplazamiento: no
existe todavía ningún objetivo de despliegue real ni datos reales (ver
[privacy-and-security.md](privacy-and-security.md) §1) — endurecer estos
puntos tiene sentido frente a un entorno de producción real concreto, no
en abstracto; se retoma cuando exista ese objetivo de despliegue. Ronda
puramente documental: sin cambios de código, sin cambios de tests.

**Fase 8 completa (8.1 + 8.2 + 8.3 + 8.4).** Los cuatro hitos quedan
cerrados: auditoría RBAC (con una desviación estructural corregida),
automatización de la purga de retención vía comando de gestión para cron
externo, decisión revisada de mantener
`AI_PROCESSING_CONSENT_ENFORCED` sin forzar, y aplazamiento documentado
de la revisión de seguridad general hasta que exista un objetivo de
despliegue real. Sin fases adicionales planificadas más allá de esta.

## Fase 9 — Autenticación real

Scope nuevo, fuera del MVP original (rama `feature/phase-9-real-auth`,
creada desde `main` ya con las Fases 7 y 8 mergeadas). Motivo: hoy
`FakeCurrentUserProvider` es la única implementación de
`CurrentUserProvider` y se rechaza estructuralmente en
`ENVIRONMENT=production` (ver
[privacy-and-security.md](privacy-and-security.md) §12) — la API no
tenía, hasta esta fase, un modo de funcionamiento válido en producción.

Alcance decidido:

- JWT Bearer en cabecera `Authorization` (no cookies de sesión) — mismo
  hueco que ocupaba `X-Dev-User-Id`.
- Alcance mínimo: login + un único token JWT de vida media (8h), sin
  refresh tokens ni blacklist de revocación. Logout es solo del lado
  cliente. Reseteo de contraseña, MFA y rate limiting del endpoint de
  login quedan fuera de esta ronda — el rate limiting conecta con la
  deuda ya documentada en el hito 8.4.
- `PyJWT` (firma/verificación) y `bcrypt` directo, sin `passlib` (hash de
  contraseña).
- Sin frontend (pantalla de login, etc.) — eso es el hito 9.2, ronda
  separada.

**Criterio de aceptación**: `POST /auth/login` con credenciales válidas
devuelve un JWT Bearer que `RealCurrentUserProvider` acepta en el resto
de endpoints; `AUTH_MODE=fake` (por defecto) no cambia nada del
comportamiento actual de `X-Dev-User-Id`.

**Estado (hito 9.1 — backend de autenticación real, cerrado)**:
`Settings` gana `auth_mode: Literal["fake", "real"] = "fake"` y
`jwt_secret_key: str` (obligatorio, sin default de Python — mismo
criterio que `postgres_password`); `_validate_production_safety` exige
`auth_mode == "real"` y rechaza `jwt_secret_key` en
`_INSECURE_DEFAULT_PASSWORDS` cuando `is_production`, mismo patrón que
el resto de guardarraíles de ese validador. `core/deps.py::
get_current_user_provider()` deja de estar hardcodeado a
`FakeCurrentUserProvider`: resuelve según `settings.auth_mode` — "fake"
sin cambios de comportamiento, "real" resuelve `RealCurrentUserProvider`
(nuevo, en `core/current_user.py`, mismo fichero que
`FakeCurrentUserProvider` — implementan el mismo `Protocol`
`CurrentUserProvider` y comparten `JWT_ALGORITHM`), que decodifica y
valida el JWT Bearer del header `Authorization`, resuelve el usuario y
exige que exista y esté activo — mismo criterio que
`FakeCurrentUserProvider`. `User` (dominio) gana `password_hash: str |
None = None`; migración Alembic `7c2e4f5a8b31` añade la columna
nullable a `users`. Nuevo módulo `app/auth/` (`service.py` + `api/`, sin
domain/infraestructura propios — mismo patrón ligero que
`RetentionCleanupService`): `AuthService.login(email, password) -> str`
busca el usuario por email, verifica el hash con `bcrypt`, verifica
`is_active`, firma un JWT (`sub=user.id`, 8h) — **mismo mensaje de error
genérico** (`UnauthenticatedError`, 401) para email inexistente,
contraseña incorrecta, usuario inactivo o sin `password_hash` asignado,
para no permitir enumerar usuarios por email. `POST /auth/login`
(`app/auth/api/`) sin autorización previa — es el propio punto de
entrada. `backend/app/seed.py` actualizado: los tres usuarios ficticios
reciben la misma contraseña de desarrollo (`DEV_USER_PASSWORD`,
documentada en el propio fichero y en `README.md`); backfillea
`password_hash` también en usuarios ya existentes de una ejecución
anterior del seed (nuevo `UserRepository.set_password_hash`), sigue
siendo idempotente. Tests nuevos: `test_auth_service.py` (credenciales
correctas, contraseña incorrecta y email inexistente comparten mensaje,
usuario inactivo, usuario sin `password_hash`), `test_current_user.py`
ampliado con `RealCurrentUserProvider` (token válido, expirado, firma
inválida, usuario inactivo/inexistente), `test_auth_api.py`
(`POST /auth/login` end-to-end) y dos casos nuevos en `test_config.py`
(`AUTH_MODE`/`JWT_SECRET_KEY` rechazados en production) — la baseline de
production válida de `test_config.py`/`test_current_user.py` se amplió
con `auth_mode="real"`/`jwt_secret_key=...` para que los tests
"production válida" existentes sigan siendo válidos con el nuevo
guardarraíl. Verificado además en vivo (contenedor real, no solo tests):
login con credenciales correctas y con contraseña incorrecta, y con
`AUTH_MODE=real` el flujo completo `POST /auth/login` → `Authorization:
Bearer` en `GET /me`, confirmando que `X-Dev-User-Id` queda rechazado en
ese modo. Suite completa (1204 tests, incluido el arreglo de canal
lateral de tiempo en `AuthService.login` — `bcrypt.checkpw` se ejecuta
siempre, exista o no el usuario, comparando contra un hash de relleno
precomputado cuando no hay `password_hash` real) en verde, ruff/black
limpios.

**Estado (hito 9.2 — pantalla de login en el frontend, cerrado)**:
`VITE_AUTH_MODE` (`fake`/`real`, por defecto `fake`) — espejo del
`AUTH_MODE` del backend, mismo mecanismo ya usado por
`VITE_API_BASE_URL` (variable de entorno leída por Vite, sin fichero
`.env.example` propio del frontend). Decisión de diseño central: el JWT
**no** repite el patrón de `devUserId` (parámetro explícito en cada
función de `shared/api/*.ts`, consumido por ~40 ficheros de
`features/*`) — se adjunta automáticamente en `client.ts` desde un
almacén de módulo fuera de React
(`shared/auth/tokenStore.ts`, variable de módulo + `sessionStorage` con
clave propia, nunca `localStorage`), así que el diff de este hito no
toca ningún fichero de `features/*` ni cambia la firma de ninguna
función existente de `shared/api/*.ts` — solo `client.ts` (adjunta
`Authorization: Bearer` en `apiRequest`/`apiDownload` cuando
`VITE_AUTH_MODE=real` y hay token; en un `401` limpia el token antes de
relanzar el error) y el `auth.ts` nuevo (`login(email, password)`, sin
`devUserId`). `shared/auth/AuthContext.tsx` (`AuthProvider`/`useAuth`,
estado de React: usuario actual, `status`) lee del mismo almacén y
resuelve `/api/v1/me` sin `devUserId` (adjuntado por `client.ts`, no por
`shared/api/devUsers.ts`, cuya firma no se toca). `shared/auth/
LoginForm.tsx`: formulario email+contraseña, mismo `ApiError` que ya
maneja el resto del frontend para mostrar el error del backend.
`App.tsx`: `VITE_AUTH_MODE=fake` (por defecto) es
`FakeAuthApp`/`DevUserProvider`, comportamiento idéntico al de antes de
esta fase; `VITE_AUTH_MODE=real` es `RealAuthApp`/`AuthProvider` —
`LoginForm` sin sesión válida, o el mismo contenido de siempre más un
botón "Cerrar sesión" donde antes vivía `DevUserSwitcher`. `AppRoutes`/
`AppNav`/`AppHeader` extraídos como componentes compartidos entre los
dos modos para que la lista de rutas sea literalmente la misma, no una
copia que pudiera divergir. Tests: `client.test.ts` ampliado (adjunta
Bearer con token en modo real, no lo adjunta en modo fake ni sin token,
limpia el token en `401`, mismo comportamiento en `apiDownload`);
`LoginForm.test.tsx` (nuevo — éxito, con una sonda de `AuthContext` que
confirma que el estado de React realmente pasa a `authenticated`;
credenciales incorrectas, mismo `ApiError` mostrado). Verificado además
en vivo (contenedor Vite real, no solo tests): la sustitución de
`import.meta.env.VITE_AUTH_MODE` llega correctamente al módulo servido
tanto en `fake` como en `real`, sin errores de arranque en ninguno de
los dos. Suite de frontend completa (223 tests) con una única falla
preexistente y no relacionada
(`apiDownload > ... Content-Disposition`, reproducida también contra el
código sin modificar — variación de fidelidad del polyfill Blob/Response
de jsdom, no un regresión de este hito); ESLint sin errores (mismo aviso
`react-refresh/only-export-components` que ya tenía `DevUserContext.tsx`,
por el mismo patrón de exportar componente + hook); Prettier limpio;
`tsc -b` sin errores.

**Fase 9 completa (9.1 + 9.2).** La API y el frontend tienen ya un modo
de funcionamiento de autenticación real, opcional vía `AUTH_MODE`/
`VITE_AUTH_MODE` — el comportamiento de desarrollo (`X-Dev-User-Id`)
sigue siendo el valor por defecto y no cambia.

## Fase 10 — Despliegue a producción (Railway)

Scope nuevo, fuera del MVP original (rama `feature/phase-10-deployment`,
creada desde `main` con las Fases 0-9 ya mergeadas). Motivo: la
aplicación tenía ya autenticación real (Fase 9), RBAC y retención (Fase
7-8), pero nunca se había ejecutado fuera de `docker compose` local — sin
integración continua, sin imágenes optimizadas para producción, sin
ningún entorno desplegado, sin observabilidad de errores en producción.

**Estado (hito 10.1 — pipeline de calidad en GitHub Actions, cerrado)**:
`.github/workflows/ci.yml`, dos jobs independientes (`backend`/
`frontend`), disparados en `pull_request` contra `main` y en `push` a
`main` (Fase 10, cierre, ver más abajo, también a `feature/**`). Backend:
Python 3.12 + Postgres 16 como servicio (health-check propio antes de
arrancar los tests), `pip install -e ".[dev]"`, `ruff check .`,
`black --check .`, `pytest`. Frontend: Node 22, `npm ci`, `npm run lint`,
`npm run format:check`, `npm run test`, `npm run build` — el build de
Vite como parte del propio CI, no solo los tests, para detectar errores
de `tsc` que los tests unitarios no cubrirían. Dos fixes que bloqueaban
el pipeline la primera vez que corrió: `audio_storage_local_dir`
asumía la ruta absoluta `/app` de Docker (rota fuera de ese contenedor,
corregida a ruta relativa) y una aserción de `client.test.ts` que
comparaba un `Blob` construido por `undici`/Node contra el `Blob` global
de jsdom — mismo dato, dos constructores de distinto realm, `instanceof`
falla aunque el contenido sea idéntico.

**Estado (hito 10.2 — imágenes Docker de producción, cerrado)**:
`backend/Dockerfile.prod` (`python:3.12-slim`, `pip install .` sin modo
editable, `gosu` instalado para el entrypoint) y
`frontend/Dockerfile.prod` (build multi-stage: `node:22-alpine` compila
con `vite build`, `nginx:alpine` sirve el resultado — `nginx.conf.template`
con cabeceras de seguridad, ver hito 10.5). Deliberadamente separadas de
los `Dockerfile` de desarrollo (sin tocar, sin hot-reload ni bind mounts
en las de producción). Fix de seguimiento: el volumen de almacenamiento
de audio montado en Railway pertenece a `root` por defecto — el
contenedor arrancaba como `root`, corregía los permisos del volumen
(`chown`) y cedía privilegios al usuario `app` no-root vía `gosu` antes
de lanzar `uvicorn` (`entrypoint.sh`), en vez de correr la aplicación
como `root` de forma permanente.

**Estado (hito 10.3 — primer despliegue en Railway, cerrado)**: creación
de los servicios de Railway (backend, frontend, Postgres) a partir de las
imágenes del hito 10.2, variables de entorno de producción configuradas
directamente en el dashboard de Railway — sin diff de código propio en
este hito (de ahí que no exista un commit dedicado; el primer commit que
lo da por hecho es el cron de retención del hito 10.4, que ya asume un
backend desplegado). Un incidente de la propia plataforma Railway obligó
a forzar un redeploy manual sin cambios de código. Deuda ya identificada
en este punto y confirmada más tarde por la auditoría de cierre (ver más
abajo): sin `railway.json` ni ningún otro artefacto de infraestructura
como código — toda la configuración vive únicamente en el dashboard de
Railway, sin versionar; y sin dominio propio, la aplicación sigue
sirviendo desde el subdominio `*.up.railway.app` generado por la
plataforma, sin certificado TLS propio.

**Estado (hito 10.4 — retención vía cron externo, cerrado)**: Railway no
permite compartir un volumen entre dos servicios distintos, así que el
proceso de retención (`RetentionCleanupService`, Fase 7.2) no puede
ejecutarse como un segundo servicio con acceso directo al volumen de
audio del backend. Nuevo endpoint `POST /api/v1/retention/system-purge`
(`app/retention/api/router.py`), autenticado por un secreto compartido
(`RETENTION_CRON_SECRET`, comparado con `secrets.compare_digest`, nunca
`==`) en vez de por un usuario de una clínica concreta — el llamador es
un Cron Job de Railway, no una persona. Servicio auxiliar mínimo
(`ops/retention-cron/`, `Dockerfile` + script Python) que solo dispara
esa llamada HTTP contra el backend ya desplegado, sin acceso propio a la
base de datos ni al volumen. `RETENTION_CRON_SECRET` sigue el mismo
patrón de guardarraíl que `JWT_SECRET_KEY`: obligatorio, sin default de
Python, rechazado en `_INSECURE_DEFAULT_PASSWORDS` en production.

**Estado (hito 10.5 — hardening HTTP, cerrado)**: cierra formalmente la
deuda aplazada en el hito 8.4 (cabeceras de seguridad, rate limiting,
límites de subida) — ahora sí existe un objetivo de despliegue real,
condición que el propio hito 8.4 fijaba para retomarlo.
`SecurityHeadersMiddleware` (`X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy`, y `Strict-Transport-Security` solo
fuera de development/test); `slowapi` para rate limiting (`Limiter` en
memoria del proceso — límite general 120/minute, `POST /auth/login` a
5/minute, `/health`/`/ready` exentos); `RequestSizeLimitMiddleware`
(techo configurable, por encima del límite específico de subida de audio
de la Fase 5); gating de `/docs`/`/redoc`/`/openapi.json` fuera de
production. Fix de seguimiento verificado en producción real: `slowapi`
identificaba al cliente por `request.client.host`, que detrás del proxy
de Railway es la IP del propio proxy (varía en cada petición) — el rate
limit de login nunca se disparaba en la práctica. Corregido leyendo el
primer valor de `X-Forwarded-For` cuando está presente, con la asunción
de confianza explícita de que todo el tráfico público pasa por el proxy
de Railway y que Railway sanea esa cabecera antes de reenviarla (nunca
un valor sin sanear que el cliente pudiera falsificar directamente).

**Estado (hito 10.6 — observabilidad: Sentry y logging estructurado,
cerrado)**: Sentry (`sentry-sdk[fastapi]` backend, `@sentry/react`
frontend) EXCLUSIVAMENTE como error tracking — sin Performance/Tracing
(`traces_sample_rate`/`tracesSampleRate` a 0 explícitamente en ambos
lados), sin Session Replay ni Profiling. Saneamiento agresivo antes de
enviar cualquier evento: cuerpo de request/response, variables locales de
traceback, cabeceras fuera de una lista blanca mínima
(`content-type`/`x-request-id`), parámetros de breadcrumbs SQL (solo la
sentencia parametrizada, nunca los valores) en el backend; en el
frontend, `integrations` en forma función (nunca array literal — un
array sustituye/pierde el mecanismo de fusión de integraciones por
defecto de forma dependiente de versión del SDK, incluida
`globalHandlersIntegration`, que captura
`window.onerror`/`unhandledrejection` — confirmado como incidente real:
un `throw` de prueba no generó ningún evento con la forma array) y
`console: false` en `breadcrumbsIntegration` (el resto de breadcrumbs
`fetch`/`xhr` ya excluyen cuerpo por diseño de la SDK). `scope.user`
limitado exclusivamente a `id` (UUID opaco) — nunca email ni
`display_name`, aunque `CurrentUser` los exponga a los dos. `release`
desde `RAILWAY_GIT_COMMIT_SHA` (variable de la propia plataforma,
poblada solo en deploys disparados desde GitHub). Activación siempre
condicionada a que `SENTRY_DSN`/`VITE_SENTRY_DSN` estén configuradas —
no-op en cualquier entorno sin ellas, backend y frontend. En paralelo,
`request_id` (ya generado por `RequestIdMiddleware` desde fases previas)
se añade como tag a cada evento Sentry de la petición en curso, y se
corrigió que no llegara al logging JSON estructurado en dos puntos que
lo omitían (`log_requests` en `app/main.py`,
`handle_unexpected_error` en `app/core/errors.py`) más tres llamadas de
`app/ai_pipeline/domain/steps/base.py` que pasaban campos sueltos en
`extra` sin anidarlos bajo `"context"` — `JsonFormatter` (que solo lee
`record.context`) los descartaba en silencio. Bug de aislamiento entre
tests descubierto al escribir estos tests de logging: `alembic/env.py`
llamaba a `logging.config.fileConfig` con su valor por defecto
(`disable_existing_loggers=True`), que deshabilita permanentemente
cualquier logger de la aplicación ya creado en el proceso y no listado en
`alembic.ini` — como los tests de migraciones ejecutan Alembic en el
mismo proceso que el resto de la suite, tras ese test ningún log de la
app volvía a propagarse durante el resto de la sesión de `pytest`;
corregido con `disable_existing_loggers=False`, sin efecto sobre
`alembic upgrade head` desde CLI (proceso propio, sin loggers previos que
proteger).

**Estado (auditoría de cierre entre fases, cerrada)**: antes de dar la
Fase 10 por completa, auditoría explícita del estado real de despliegue
frente a lo documentado. Hallazgos: (1) el pipeline de CI (hito 10.1)
solo corría en `pull_request`/`push` a `main` — cualquier problema en una
rama `feature/**` no se detectaba hasta abrir el PR; corregido añadiendo
`feature/**` a `push.branches` en `ci.yml`. (2) no existía ningún entorno
de staging — toda verificación manual se hacía contra producción
directamente o no se hacía; resuelto en el hito 10.7. (3) sin
`railway.json` ni ningún otro artefacto de infraestructura como código —
deuda ya señalada en el hito 10.3, confirmada aquí, no repetida dos veces
por descuido. (4) sin dominio propio — deuda igualmente ya señalada en el
hito 10.3. (5) el rate limiting de `POST /auth/login` — que
[privacy-and-security.md](privacy-and-security.md) §11 documentaba
todavía como parte de la deuda aplazada del hito 8.4 — llevaba ya
implementado desde el hito 10.5 (5/minute); la entrada de deuda de ese
documento había quedado obsoleta sin que nadie la actualizara al cerrar
el hito 10.5. Ronda con un único cambio de código (el fix de CI); el
resto son hallazgos documentales, corregidos donde se detectó que la
documentación ya no reflejaba la realidad.

**Estado (hito 10.7 — entorno de staging, cerrado)**: `Settings.environment`
gana un cuarto valor literal, `"staging"` (antes
`Literal["development", "test", "production"]`), y una property
`is_staging` nueva junto a `is_production`. `_validate_production_safety`
pasa a evaluarse si `is_production` **o** `is_staging` — las mismas
validaciones (CORS sin comodín, `POSTGRES_PASSWORD`/`JWT_SECRET_KEY`/
`RETENTION_CRON_SECRET` fuera de la lista insegura, `AUTH_MODE=real`
obligatorio, bloque de consentimiento/límite de coste LLM si hay algún
proveedor LLM real activo) aplican igual en los dos entornos — un entorno
de staging con las mismas fugas potenciales que production no protege
nada. Mismo criterio propagado a `FakeCurrentUserProvider` (rechaza
`is_production` **o** `is_staging`, mensaje de error generalizado a los
dos), `register_dev_tools` (no-op en los dos) y
`hsts_enabled=settings.is_production or settings.is_staging` en
`SecurityHeadersMiddleware`. Deliberadamente sin tocar: `app/seed.py`
(el seed de usuarios ficticios sigue permitido en staging — necesario
para poder entrar a probarlo) y `_docs_kwargs_for` en `app/main.py` (los
docs interactivos siguen visibles fuera de production, staging incluido).

Antes de llegar a esta implementación se intentó activar **"PR
Environments" de Railway** — entornos efímeros creados automáticamente
por cada Pull Request, que se habrían destruido solos al cerrarlo. Los
permisos de la GitHub App de Railway se verificaron correctos y se
provocó el disparador varias veces (la mayoría sin commit propio, vía
dashboard), pero el entorno nunca llegó a crearse por una causa no
identificada tras varias pruebas — **deuda documentada, sin resolver**,
no investigada más a fondo para no bloquear el resto del cierre de la
fase. El único commit vacío dedicado a este intento,
`chore: trigger PR Environment` (`d230329`), queda fechado ya después del
commit que implementa el staging persistente (`d9cdb9c`) — coherente con
que fuera el último intento de confirmación y no el primero de la serie,
aunque el orden exacto de los intentos previos sin commit no quedó
registrado con precisión. Se optó en su lugar por un entorno de staging
**persistente**, creado por duplicación manual del servicio de
production en el dashboard de Railway, con variables propias:
`JWT_SECRET_KEY` distinto (nunca compartido con production),
`BACKEND_CORS_ORIGINS`/`VITE_API_BASE_URL` propios del subdominio de
staging, `ENVIRONMENT=staging`, `VITE_SENTRY_ENVIRONMENT=staging` (ver
más abajo), cron de retención **desactivado** (datos de staging no
sujetos a la misma política de retención que production) y el seed de
usuarios ficticios **sí activo** (a diferencia de production, donde
`app/seed.py` se rechaza estructuralmente).

Un efecto colateral encontrado al verificar Sentry en staging:
`import.meta.env.MODE` (modo de build de Vite) vale `"production"` tanto
en el build de producción como en el de staging — ambos ejecutan
`vite build` sin distinción — así que Sentry etiquetaba los eventos de
staging como si fueran de production. Corregido con
`VITE_SENTRY_ENVIRONMENT` (opcional, sin romper ningún entorno que no la
defina — cae a `import.meta.env.MODE`), inyectada por servicio en
`frontend/Dockerfile.prod` igual que `VITE_SENTRY_DSN`.

**Estado (dos bugs reales de producción, descubiertos al verificar
staging manualmente, cerrados)**: ninguno de los dos lo causó el trabajo
de esta fase — ya estaban en producción, solo que nunca se habían
probado con `VITE_AUTH_MODE=real` fuera de los tests automáticos.
(1) `useDevUser()` (`shared/devUser/DevUserContext.tsx`) se llamaba sin
condiciones desde once páginas de `AppRoutes` (`PatientsPage`,
`ClinicalSessionsPage` y el resto), pero `RealAuthApp` nunca monta
`<DevUserProvider>` — cualquier usuario real que navegara a `/patients`
(o cualquiera de las otras diez) recibía una pantalla en blanco con
`"useDevUser debe usarse dentro de <DevUserProvider>"`. Corregido
haciendo que `useDevUser()` derive el mismo shape del usuario autenticado
vía un nuevo `useAuthOptional()` (variante de `useAuth()` que no lanza si
no hay `<AuthProvider>`) cuando no hay `<DevUserProvider>` montado — el
modo fake queda intacto, las once páginas no se tocaron. (2) no existía
ningún endpoint real (autenticado) para listar los usuarios elegibles
como "profesional responsable" de una sesión clínica —
`useProfessionalOptions` dependía en exclusiva de `GET /api/v1/dev/users`,
exclusivo de desarrollo y ya deshabilitado en production desde antes de
esta fase — así que crear cualquier sesión clínica como usuario real
estaba roto (campo obligatorio, desplegable siempre vacío). Corregido con
`GET /api/v1/clinical-sessions/eligible-professionals` (misma regla que
`ClinicalSessionService._validate_professional`: misma clínica, activo,
rol admin/audiologist), y `useProfessionalOptions` eligiendo entre ese
endpoint y `GET /dev/users` según qué esté realmente montado en el árbol
— mismo criterio que el bug anterior, nunca releer `VITE_AUTH_MODE`.

**Estado (verificación manual completa en staging, cerrada)**: login con
credenciales reales, creación de una sesión clínica completa y subida de
audio con transcripción real contra Deepgram
(`https://api.eu.deepgram.com`, endpoint UE, ver
[transcription-benchmark.md](transcription-benchmark.md)). Esta
verificación reveló que, hasta este punto, `TRANSCRIPTION_PROVIDER`
seguía en `mock` en **todos** los entornos, incluida production — las
variables `ASSEMBLYAI_API_KEY`/`DEEPGRAM_API_KEY` de Railway seguían con
el valor placeholder `CHANGE_ME_LOCAL_ONLY` de `.env.example`, pese a que
ambos proveedores están integrados y disponibles desde la Fase 5/5.3.
Decisión: activar el proveedor real (Deepgram) **solo en staging**, dejando
production deliberadamente en `mock` hasta que exista una decisión de
negocio explícita sobre el lanzamiento — no es un olvido, es una elección
consciente para no facturar contra una clave real sin haber decidido
todavía vender el producto. Política acordada para el manejo de esta
clave real en staging (documentada también en
[privacy-and-security.md](privacy-and-security.md) §10): (1) heredar
claves reales de un proveedor está permitido temporalmente en staging;
(2) ninguna prueba automática (CI, suite de tests) debe poder disparar
una transcripción real — la suite completa sigue usando exclusivamente
`MockTranscriptionProvider`; (3) las pruebas manuales contra staging
deben ser deliberadamente mínimas, nunca una fuente sistemática de
tráfico; (4) debe quedar documentado que consumen cuota/facturación real
del proveedor. Se sustituirán por credenciales de sandbox si
AssemblyAI/Deepgram llegan a ofrecerlas más adelante.

**Fase 10 completa.** CI/CD, imágenes de producción, despliegue real en
Railway (production + staging), retención vía cron externo, hardening
HTTP, observabilidad de errores con saneamiento de PHI, y un entorno de
staging persistente que ya sirvió para encontrar y cerrar dos bugs reales
de producción antes de que los encontrara un usuario real. **Deuda
documentada explícitamente, aplazada, no oculta:**

- **PR Environments de Railway sin funcionar** — permisos verificados
  correctos, disparado varias veces, nunca se crea el entorno; causa no
  identificada. Se sigue con el staging persistente mientras tanto.
- **Sin dominio propio ni TLS custom** — la aplicación sirve desde
  `*.up.railway.app` en production y en staging.
- **Sin `railway.json` ni infraestructura como código** — toda la
  configuración de los servicios de Railway vive únicamente en su
  dashboard, sin versionar ni reproducible desde el repositorio.
- **Proveedor de transcripción real activo solo en staging** — production
  sigue en `mock`, pendiente de una decisión de negocio explícita antes
  de vender el producto (ver más arriba).

## Fuera de las fases del MVP

Cualquier integración real (Noah, calendario, o cualquier proveedor de
modelo de lenguaje de pago — OpenAI, Anthropic, Claude API, Gemini,
Ollama, Llama), multi-tenant, selector de idioma en tiempo de ejecución
(más allá de centralizar textos para prepararlo, ver
[architecture.md](architecture.md) §8), grabación en vivo, scheduler
automático de retención (Fase 7 solo prepara la interfaz, Fase 8 la
automatiza si el tiempo lo permite), bloqueo forzado por
consentimiento de IA (preparado en la Fase 4, no forzado hasta que se
decida explícitamente) o firma electrónica avanzada quedan fuera de este
plan (ver [product-requirements.md](product-requirements.md) §4) y
requerirían un nuevo ciclo de análisis de alcance — o, en el caso de un
proveedor de IA real, además un acuerdo de tratamiento de datos previo —
antes de planificarse.

**Excepción ya decidida: AssemblyAI (Fase 5) y Deepgram (Fase 5.3).** El
párrafo anterior excluía "cualquier proveedor de transcripción... de
pago" de forma genérica; esa exclusión quedó superada explícitamente en
la Fase 5 (AssemblyAI) y de nuevo en la Fase 5.3 (Deepgram), cada una el
"nuevo ciclo de análisis de alcance" que este mismo párrafo pedía como
condición. AssemblyAI y Deepgram son, ambos, proveedores de transcripción
integrados en el pipeline real (`POST /audio-recordings/{id}/transcribe`,
seleccionables vía `TRANSCRIPTION_PROVIDER=assemblyai|deepgram`) — cuál
de los dos se recomienda para producción queda pendiente de la
comparación de 3 vías (§Fase 5.3, bloqueada por `DEEPGRAM_API_KEY`, ver
[transcription-benchmark.md](transcription-benchmark.md) §20). El resto
de proveedores listados en
[transcription-benchmark.md](transcription-benchmark.md) (OpenAI,
Speechmatics, Azure Speech, Google Speech, AWS Transcribe, Whisper local)
quedan preparados únicamente para `benchmark/` — ninguno está integrado
en el pipeline real, y añadirlo ahí seguiría exigiendo este mismo ciclo
de análisis de alcance, sesión por sesión.
