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
  transcription/  → TranscriptionProvider ──▶ MockTranscriptionProvider (MVP)
  anamnesis/…      → LanguageModelProvider ──▶ MockLanguageModelProvider (MVP)
  integrations/    → PatientRecordIntegration ──▶ MockPatientRecordIntegration (MVP)
                    → CalendarIntegration ──▶ MockCalendarIntegration (MVP)
  session_notes/…  → DocumentExporter ──▶ PdfDocumentExporter / TextDocumentExporter
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
    audio/
      domain/
        audio_storage.py        # interfaz AudioStorage (puerto)
        validation.py            # reglas de tamaño/duración/extensión/MIME
        retention.py              # interfaz RetentionCleanupService
      infrastructure/
        local_audio_storage.py  # única implementación en el MVP
    transcription/
    anamnesis/
    session_notes/
    clinical_flags/
      domain/
        clinical_flag_ruleset.py     # interfaz ClinicalFlagRuleset (puerto)
      infrastructure/
        demo_clinical_flag_ruleset.py # checklist genérico, no validado
    integrations/
      domain/            # interfaces abstractas compartidas
        transcription_provider.py
        language_model_provider.py
        patient_record_integration.py
        calendar_integration.py
        document_exporter.py
      mocks/
        mock_transcription_provider.py
        mock_language_model_provider.py
        mock_patient_record_integration.py
        mock_calendar_integration.py
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

`AudioStorage` y `ClinicalFlagRuleset` son interfaces igual de "abstractas
obligatorias" que las de `integrations/`, pero se definen dentro de su
propio módulo (`audio`, `clinical_flags`) porque no son integraciones con
sistemas externos de terceros — son puntos de extensión internos del
dominio. `integrations/` queda reservado a las cuatro interfaces e
implementaciones mock originales (transcripción, LLM, historia clínica,
calendario) más el exportador de documentos.

## 3. Módulos de dominio

| Módulo | Responsabilidad |
|---|---|
| `clinics` | Entidad `Clinic` mínima; sistema multi-clínica desde el modelo, sin gestión completa desde el frontend en el MVP (Fase 2). |
| `users` | Usuarios internos (`admin`/`audiologist`/`viewer`) por clínica. Sin autenticación real: solo resolución vía `CurrentUserProvider` (Fase 2). |
| `patients` | Identidad y datos administrativos mínimos del paciente (ficticio), aislados por clínica. No contiene contenido clínico. |
| `clinical_sessions` | Entidad central de la consulta: pertenece a una clínica, un paciente y un profesional responsable. Máquina de estados propia (`ClinicalSessionStatus`, Fase 3, diseño en [data-model.md](data-model.md) §8), borrado lógico (`is_archived`) independiente del estado. Base sobre la que se colgarán audio, transcripción, anamnesis, notas, señales clínicas, etc. en fases posteriores. |
| `audio` | Subida, validación (tamaño/duración/extensión/MIME) y almacenamiento de la grabación vía `AudioStorage`, incluida su eliminación física conforme a retención. |
| `transcription` | Orquesta la llamada a `TranscriptionProvider` y persiste el resultado. |
| `anamnesis` | Genera (vía `LanguageModelProvider`) y gestiona el ciclo de vida del documento de anamnesis, con versionado, `schema_version` y borrado lógico si está aprobado. |
| `session_notes` | Resumen profesional de la sesión, mismo ciclo de vida que anamnesis (versionado, borrado lógico). |
| `clinical_flags` | Señales de alerta / posibles motivos de derivación, generadas por un `ClinicalFlagRuleset` sustituible (MVP: checklist de demostración no validado clínicamente), con estado de revisión humana. |
| `audit_log` | Registro append-only (tabla `audit_logs`) de acciones relevantes sobre pacientes, sesiones y documentos, escrito en la misma transacción que la entidad auditada. |
| `integrations` | Interfaces abstractas + mocks para proveedores externos (transcripción, LLM, Noah, calendario) y exportadores de documentos. |

## 4. Interfaces abstractas obligatorias

Definidas en `integrations/domain/`, implementadas en el MVP únicamente por
sus contrapartes `Mock*`:

- **`TranscriptionProvider`**: `transcribe(audio_file) -> TranscriptionResult`.
- **`LanguageModelProvider`**: `generate_anamnesis(transcript) -> AnamnesisDraft`,
  `generate_session_summary(transcript) -> str`,
  `detect_missing_information(anamnesis_draft) -> list[MissingInfoItem]`,
  `detect_clinical_flags(transcript) -> list[ClinicalFlagDraft]`.
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
- **`RetentionCleanupService`** (`audio/domain/retention.py`):
  `find_expired_audio(now) -> list[AudioRecording]`,
  `purge(audio_recording_id) -> None` — borrado físico del audio +
  invalidación de `storage_reference`, con entrada de auditoría. En el MVP
  se invoca manualmente (endpoint/admin), sin scheduler.
- **`ClinicalFlagRuleset`** (`clinical_flags/domain/`):
  `evaluate(transcript, anamnesis_draft) -> list[ClinicalFlagDraft]`. MVP:
  `DemoClinicalFlagRuleset`, checklist genérico marcado explícitamente como
  no validado clínicamente (ver [clinical-safety.md](clinical-safety.md)).

Cada interfaz se selecciona en tiempo de ejecución mediante configuración
(inyección por variable de entorno / factory), nunca mediante `import`
directo del módulo consumidor a la implementación concreta.

## 5. Estados de procesamiento (`ProcessingStatus`) y máquinas de estado propias

Se define un enumerado compartido en `core/processing_status.py` con, como
mínimo: `uploaded`, `validating`, `ready`, `transcribing`, `transcribed`,
`generating`, `review_pending`, `approved`, `failed`, `deleted`. Cada
entidad con ciclo de vida basado en procesamiento (`audio_recordings`,
`anamnesis_documents`, `session_notes` — fases futuras, sin implementar
todavía) usa el subconjunto de estados que le aplica.

Las transiciones válidas (p. ej. `uploaded → validating → ready`, nunca
`uploaded → approved`) se definen y verifican en la **capa de dominio o
servicio** de cada módulo (una función/objeto `StateMachine` por entidad),
no únicamente mediante validación en el router de FastAPI. Cualquier
intento de transición inválida lanza una excepción de dominio antes de
tocar la base de datos. Detalle completo de estados por entidad en
[data-model.md](data-model.md) §6.

`clinical_flags` mantiene su propio eje de estado independiente
(`sugerida_ia` / `confirmada_por_profesional` / `descartada`): no es un
estado de *procesamiento* sino de *disposición del profesional* ante una
señal, y no se mezcla con `ProcessingStatus`.

**`clinical_sessions` no usa `ProcessingStatus`.** Tiene su propia máquina
de estados, `ClinicalSessionStatus` (`scheduled`, `in_progress`,
`completed`, `review_pending`, `reviewed`, `cancelled`), definida en
`clinical_sessions/domain/state_machine.py` y documentada en
[data-model.md](data-model.md) §8. Razón: el vocabulario de
`ProcessingStatus` (pensado para un pipeline lineal de IA:
subir→validar→procesar→revisar→aprobar) no expresa bien el ciclo de vida
real de una consulta clínica — creación directa en varios estados,
cancelación, o el hecho de que "revisar" aquí no depende de ningún
proveedor de IA. Mismo principio arquitectónico (transiciones validadas en
dominio/servicio, nunca solo en el router), vocabulario y reglas propias.
Esta es una corrección respecto al diseño original de la Fase 0/1, que
trataba `clinical_sessions` como un agregado informativo de
`ProcessingStatus`; ver nota en [data-model.md](data-model.md) §6.

## 6. Flujo end-to-end (secuencia principal)

1. El profesional crea un paciente ficticio.
2. Crea una `ClinicalSession` asociada a ese paciente (estado `created`).
3. Sube un audio → `audio` valida tamaño/duración/extensión/MIME
   (`uploaded` → `validating` → `ready`, o `failed` si no pasa la
   validación) y lo almacena vía `AudioStorage`.
4. El profesional solicita transcripción → `transcription` invoca
   `TranscriptionProvider.transcribe(...)` (`transcribing` → `transcribed`,
   o `failed`).
5. El profesional solicita generación de documentos → `anamnesis` y
   `session_notes` invocan `LanguageModelProvider`, y `clinical_flags`
   invoca `ClinicalFlagRuleset` (`generating` → `review_pending`, o
   `failed`).
6. El profesional revisa/edita cada documento → cada guardado crea una
   nueva versión (`document_versions`); el documento permanece en
   `review_pending` hasta la aprobación explícita.
7. El profesional aprueba explícitamente → estado `approved`, se registra
   usuario y timestamp. Solo entonces el documento puede exportarse. Una
   nueva edición tras la aprobación devuelve el documento a
   `review_pending` y exige nueva aprobación.
8. `audit_log` registra cada transición de estado y cada edición relevante
   durante todo el flujo, incluidos fallos y borrados.
9. El profesional exporta anamnesis/resumen aprobados vía
   `DocumentExporter` (`exported` a nivel de sesión, informativo).
10. Pasado el periodo de retención (30 días por defecto), el audio puede
    eliminarse físicamente (`deleted`) de forma manual vía
    `RetentionCleanupService`; los documentos clínicos aprobados nunca se
    eliminan físicamente, solo mediante borrado lógico auditado.

## 7. Frontend

Estructura por pantallas/flujo, no por tipo de componente:

```
frontend/
  src/
    features/
      patients/
      sessions/
      audio-upload/
      transcription/
      anamnesis-review/
      session-notes-review/
      clinical-flags/
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

- **Backend**: todos los textos fijos (avisos obligatorios de IA,
  disclaimers del checklist de señales de alerta, plantillas/prompts del
  `LanguageModelProvider`) viven en `core/messages/es.py` como constantes
  con clave semántica (p. ej. `AI_DISCLAIMER`, `CLINICAL_FLAGS_DEMO_NOTICE`),
  nunca como literales repetidos en el código de dominio.
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
  módulo clínico (`anamnesis`, `clinical_flags`, etc.) independiente y más
  fácil de razonar/testear de forma aislada.
- **Versionado explícito de documentos** (no solo `updated_at`): requisito
  de negocio (guardar original IA + versión final) y de auditoría clínica.
- **Identidad del paciente separada del contenido clínico** (módulo
  `patients` vs. resto de módulos clínicos que solo referencian
  `patient_id`): principio de privacidad desde el diseño, ver
  [privacy-and-security.md](privacy-and-security.md) y
  [data-model.md](data-model.md).
- **Un único backend modular (monolito modular)** en vez de microservicios:
  el MVP no tiene el volumen ni el equipo que justifique la complejidad
  operativa de microservicios; los límites de módulo ya preparan una
  futura extracción si hiciera falta.
- **`AudioStorage` y `ClinicalFlagRuleset` como interfaces internas del
  módulo, no en `integrations/`**: no son integraciones con sistemas
  externos de terceros sino puntos de extensión propios del dominio
  (almacenamiento físico, protocolo clínico). Mezclarlas con
  `integrations/` diluiría el propósito de ese módulo (reservado a Noah,
  calendario, transcripción y LLM).
- **`ProcessingStatus` compartido con transiciones validadas en
  dominio/servicio**: exigido para poder razonar sobre el estado de una
  sesión de forma consistente en todos los módulos y para que ninguna
  transición inválida (p. ej. aprobar un documento sin generarlo antes)
  dependa solo de que el frontend "se porte bien".
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
