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
verde del hito 8.2. Hito 8.4 (hardening general) queda para la
siguiente ronda, sin empezar.

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
