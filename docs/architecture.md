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
    patients/
      domain/
      infrastructure/
      api/
    clinical_sessions/
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
    users/
    audit_log/
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
      security.py          # auth, hashing, RBAC
      db.py                 # engine/session SQLAlchemy
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
| `patients` | Identidad mínima del paciente (ficticio). No contiene contenido clínico. |
| `clinical_sessions` | Ciclo de vida de una sesión clínica asociada a un paciente y un profesional. |
| `audio` | Subida, validación (tamaño/duración/extensión/MIME) y almacenamiento de la grabación vía `AudioStorage`, incluida su eliminación física conforme a retención. |
| `transcription` | Orquesta la llamada a `TranscriptionProvider` y persiste el resultado. |
| `anamnesis` | Genera (vía `LanguageModelProvider`) y gestiona el ciclo de vida del documento de anamnesis, con versionado, `schema_version` y borrado lógico si está aprobado. |
| `session_notes` | Resumen profesional de la sesión, mismo ciclo de vida que anamnesis (versionado, borrado lógico). |
| `clinical_flags` | Señales de alerta / posibles motivos de derivación, generadas por un `ClinicalFlagRuleset` sustituible (MVP: checklist de demostración no validado clínicamente), con estado de revisión humana. |
| `users` | Usuarios internos, roles, autenticación. |
| `audit_log` | Registro append-only de acciones relevantes sobre pacientes, sesiones y documentos. |
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

## 5. Estados de procesamiento (`ProcessingStatus`)

Se define un enumerado compartido en `core/processing_status.py` con, como
mínimo: `uploaded`, `validating`, `ready`, `transcribing`, `transcribed`,
`generating`, `review_pending`, `approved`, `failed`, `deleted` — más
`created` y `exported` como extensiones necesarias para el estado inicial
de una sesión y su cierre. Cada entidad con ciclo de vida
(`clinical_sessions`, `audio_recordings`, `anamnesis_documents`,
`session_notes`) usa el subconjunto de estados que le aplica.

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

## 9. Decisiones de arquitectura y por qué

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
