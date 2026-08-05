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
`transcription`, `anamnesis`, `session_notes`, `clinical_flags` ni ningún
proveedor mock funcional — esos módulos quedan vacíos de lógica de negocio
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
11. No se implementa nada de `clinical_sessions`, `audio`,
    `transcription`, `anamnesis`, `session_notes`, `clinical_flags`,
    integraciones ni autenticación real.
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
11. No se implementa nada de `audio`, `transcription`, `anamnesis`,
    `session_notes`, `clinical_flags`, integraciones, autenticación real
    ni frontend de `clinical_sessions` (queda para una ronda posterior).
12. No se usan datos reales en ningún punto.

## Fase 4 — `audio`

- Módulo `audio`: interfaz `AudioStorage` + `LocalAudioStorage`; subida
  multipart; validación de tamaño/duración/extensión/MIME
  (`AUDIO_MAX_SIZE_MB`, `AUDIO_MAX_DURATION_MINUTES`); metadatos y
  checksum en `audio_recordings` (sin blob en PostgreSQL).
- Requiere una `clinical_session` existente (Fase 3) sobre la que colgar
  el audio.
- Pantallas: subir audio desde el detalle de una sesión, con feedback de
  validación.

**Criterio de aceptación**: desde una sesión clínica se sube un audio
ficticio de prueba; el audio pasa por
`uploaded → validating → ready` (o `failed` si no cumple los límites).

## Fase 5 — `transcription` (mock)

- Interfaz `TranscriptionProvider` + `MockTranscriptionProvider`
  (transcripción determinista/fixture, sin IA real).
- Endpoint para disparar transcripción y consultar resultado; exige audio
  en `ready`.
- Pantalla: ver transcripción de una sesión.

**Criterio de aceptación**: al disparar la transcripción de un audio
`ready`, se obtiene y persiste un texto de ejemplo determinista; el audio
progresa `transcribing → transcribed`.

## Fase 6 — `anamnesis`, `session_notes`, `clinical_flags` (generación mock)

- Interfaz `LanguageModelProvider` + `MockLanguageModelProvider` que, a
  partir de fixtures de transcripción, genera anamnesis estructurada
  (todos los campos y estados de [data-model.md](data-model.md) §3, con
  `schema_version`), resumen de sesión, respetando el lenguaje de
  [clinical-safety.md](clinical-safety.md).
- Interfaz `ClinicalFlagRuleset` + `DemoClinicalFlagRuleset` (checklist
  genérico no validado clínicamente, ver
  [clinical-safety.md](clinical-safety.md) §7), aislada del
  `LanguageModelProvider`.
- Endpoints de generación y consulta para los tres módulos
  (`generating → review_pending`/`failed`).
- Tests que verifiquen: ausencia de lenguaje prohibido, presencia del
  aviso obligatorio (y del aviso específico del checklist demo), y que
  ningún campo se marque `informado` sin fragmento de respaldo.
- Pantallas: ver anamnesis generada, resumen generado, lista de señales de
  alerta con ambos avisos — todo en modo solo lectura por ahora (la
  edición llega en Fase 6).

**Criterio de aceptación**: a partir de una transcripción de prueba se
generan los tres documentos, visibles en la UI con los avisos de IA y de
checklist no validado.

## Fase 7 — Revisión, edición, aprobación, versionado, `audit_log`

- `document_versions` funcionando para anamnesis y resumen.
- Endpoints `PUT` (guardar edición) y `POST /approve` para ambos, con la
  transición `approved → review_pending` al editar tras aprobar.
- Borrado lógico (`DELETE`) de anamnesis/resumen/sesión: `status →
  deleted`, nunca borrado físico.
- Módulo `audit_log`: registro de las acciones listadas en
  [privacy-and-security.md](privacy-and-security.md) §6, incluidos fallos
  y borrados.
- Pantalla: edición inline de anamnesis/resumen, botón de aprobación
  explícita, vista de historial de versiones, vista de auditoría (rol
  admin) para una sesión.
- Endpoint y pantalla para cambiar estado de `clinical_flags`
  (confirmar/descartar).

**Criterio de aceptación**: se puede editar un campo de la anamnesis,
guardar (queda `review_pending`, se crea versión nueva), y aprobar
explícitamente (queda `approved`, con usuario y fecha visibles). Editar de
nuevo tras aprobar exige nueva aprobación. El historial muestra la versión
original de IA y la versión editada.

## Fase 8 — Exportación

- Interfaz `DocumentExporter` con `PdfDocumentExporter` y
  `TextDocumentExporter`.
- Endpoints de exportación, bloqueados si el documento no está `approved`.
- Pantalla: botón de exportar (PDF/texto) visible solo cuando corresponde.

**Criterio de aceptación**: un documento aprobado se descarga como PDF y
como texto plano con formato legible; un documento no aprobado devuelve
error controlado y la UI no ofrece la opción.

## Fase 9 — `integrations` (interfaces + mocks), `consents`, retención

- Interfaces `PatientRecordIntegration` y `CalendarIntegration` +
  `Mock*`, sin llamadas de red reales.
- Endpoints de configuración de integraciones (`GET/PATCH /integrations`).
- Modelo y endpoints de `consents`.
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

## Fase 10 — RBAC más fino, scheduler de retención, hardening

- Revisión de permisos por endpoint según
  [privacy-and-security.md](privacy-and-security.md).
- Automatización opcional (scheduler/cron) sobre el
  `RetentionCleanupService` ya existente desde la Fase 9 — el servicio no
  cambia, solo se añade quién lo invoca periódicamente.
- Revisión de seguridad general (dependencias, cabeceras HTTP, límites de
  tamaño de subida, rate limiting básico si el tiempo lo permite).

**Criterio de aceptación**: checklist de
[privacy-and-security.md](privacy-and-security.md) revisado punto por
punto contra el estado real del código, con desviaciones documentadas
explícitamente si las hay.

## Fuera de las fases del MVP

Cualquier integración real (Noah, calendario, proveedor de transcripción o
LLM de pago), multi-tenant, selector de idioma en tiempo de ejecución
(más allá de centralizar textos para prepararlo, ver
[architecture.md](architecture.md) §8), grabación en vivo, scheduler
automático de retención (Fase 9 solo prepara la interfaz, Fase 10 la
automatiza si el tiempo lo permite) o firma electrónica avanzada quedan
fuera de este plan (ver [product-requirements.md](product-requirements.md)
§4) y requerirían un nuevo ciclo de análisis de alcance antes de
planificarse.
