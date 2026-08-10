# AI Pipeline — arquitectura oficial

## 0. Estado de este documento

**Diseño cerrado el 2026-08-10.** Las decisiones de este documento son
arquitectura oficial del proyecto, con el mismo estatus que el diseño de
`clinical_sessions` en [data-model.md](data-model.md) §8. Sustituye por
completo al diseño previamente esbozado (no implementado) de módulos
independientes `transcription`/`anamnesis`/`session_notes`/`clinical_flags`
con tablas propias y `document_versions` polimórfica — esa versión anterior
queda eliminada de la documentación, sin dejar dos arquitecturas posibles.

**Qué no cambia**: el módulo `audio` (subida, validación, almacenamiento
local) sigue siendo una pieza de infraestructura separada, sin rediseñar
aquí — ver [development-plan.md](development-plan.md) Fase 4.1. Este
documento diseña lo que ocurre **a partir de** una transcripción
disponible, no la subida de audio en sí.

**Qué no se implementa todavía.** Ningún proveedor real (Whisper, OpenAI,
Claude API, Anthropic API, Gemini, Ollama, Llama u otra API externa),
subida de audio, micrófono, almacenamiento definitivo de audio ni
transcripción real. Todo lo descrito aquí se implementa, en las subfases
de [development-plan.md](development-plan.md) Fase 4, únicamente mediante
implementaciones `Mock*`.

**Dónde vive cada cosa.** Este documento es la referencia de dominio,
interfaces, orquestación, contratos y secuencia del AI Pipeline. El
**esquema de tablas** (columnas, tipos, índices) es responsabilidad de
[data-model.md](data-model.md) §10-12 — no se duplica aquí, siguiendo el
mismo criterio ya usado para `clinical_sessions` (su esquema vive
íntegramente en data-model.md, no en un documento aparte). Este documento
enlaza a data-model.md para el detalle exacto de columnas.

Documentos actualizados para integrar este diseño:
[architecture.md](architecture.md) §2-6, [data-model.md](data-model.md)
§2 y §10-12, [api-specification.md](api-specification.md) sección "AI
Pipeline", [privacy-and-security.md](privacy-and-security.md) §3-9,
[development-plan.md](development-plan.md) Fase 4.

---

## 1. Análisis del dominio

### 1.1 Qué es un "artefacto de IA"

Una `ClinicalSession` genera, mediante IA, varios documentos de apoyo:
una transcripción, un resumen, información ausente sugerida, señales de
alerta y una anamnesis estructurada. Todos comparten el mismo ciclo de
vida conceptual, independientemente de su contenido:

1. Se genera automáticamente a partir de una entrada (transcripción, u
   otro artefacto ya generado).
2. El resultado **nunca se considera definitivo por sí solo** — exige
   revisión humana explícita (regla no negociable, ver
   [clinical-safety.md](clinical-safety.md) §5).
3. Puede editarse, aprobarse, rechazarse o regenerarse, **sin perder**
   ninguna versión anterior.
4. Cada generación queda auditada: proveedor, modelo, coste, tiempo,
   prompt usado.
5. La IA nunca escribe directamente sobre el "expediente" — solo produce
   borradores que un profesional aprueba explícitamente:

```
AI → Draft → Human Review → Approve → Persist

Nunca:
AI → Database
```

Este patrón se repite idéntico para los cinco artefactos actuales y para
cualquier artefacto futuro. **Decisión cerrada**: se modela mediante una
entidad genérica `AIArtifact` (§3), no mediante una tabla por tipo.

### 1.2 `clinical_flags`: por qué sigue siendo una proyección aparte

| Artefacto | Disposición de revisión |
|---|---|
| Transcripción, resumen, información ausente, anamnesis | Documento único (aprobar/rechazar/editar el artefacto completo) |
| Señales de alerta (`clinical_flags`) | **Por ítem**: cada señal generada se confirma o descarta individualmente |

`clinical_flags` no encaja en "aprobar/rechazar el artefacto completo".
**Decisión cerrada**: `AIArtifact`/`AIArtifactVersion` cubren la capa de
**generación y auditoría** de `clinical_flags` (qué generó la IA, cuándo,
con qué coste — igual que cualquier otro artefacto), mientras que la
tabla `clinical_flags` ya existente en
[data-model.md](data-model.md) §2 sigue siendo, sin cambios, la capa de
**disposición humana por ítem**, poblada a partir del contenido de la
versión generada. Dos capas, no una tabla genérica forzando una única
disposición por documento.

### 1.3 `MissingInformationGenerator`: alcance frente a la anamnesis

Con el nuevo orden del pipeline (§1.4), `MissingInformationGenerator` se
ejecuta **antes** de generar la anamnesis estructurada, no después. Su
salida no es "qué campos quedaron vacíos en la anamnesis" (eso ya no
puede calcularse, porque la anamnesis todavía no existe), sino un
análisis independiente, a partir del resumen y las señales detectadas, de
qué información conviene ampliar — que después alimenta a
`AnamnesisGenerator` para producir un borrador más completo y consciente
de sus propias lagunas. Esto resuelve de raíz la redundancia que existía
en el diseño anterior (donde `informacion_ausente` era un campo derivado
*dentro* de la propia anamnesis): ahora es un artefacto independiente,
generado primero, que informa a la anamnesis en vez de derivarse de ella.

### 1.4 El pipeline es un grafo de dependencias, no una cadena lineal

**Decisión cerrada.** Grafo de dependencias oficial:

```
ClinicalSession
      │
      ▼
    Audio                    (módulo aparte, sin cambios — Fase 4.1)
      │
      ▼
 Transcription                (artifact_type = transcript)
      │
      ├────────────────┐
      ▼                ▼
   Summary       Clinical Flags
      │                │
      └───────┬────────┘
              ▼
     Missing Information
              │
              ▼
     Structured Anamnesis      (artifact_type = anamnesis)
```

Cada paso declara **únicamente** sus propias dependencias
(`depends_on()`, §6.2) — nunca conoce al orquestador ni a los pasos que
dependen de él:

| Paso | `depends_on()` |
|---|---|
| Transcription | `{}` (requiere `Audio`, prerrequisito externo al pipeline) |
| Summary | `{transcript}` |
| Clinical Flags | `{transcript}` |
| Missing Information | `{summary, clinical_flags}` |
| Structured Anamnesis | `{missing_information}` (y, además, el propio `transcript` como texto fuente — ver §6.1, `AnamnesisGenerator` recibe ambos) |

**Decisión cerrada**: el orquestador de la Fase 4.5 (`SequentialPipelineOrchestrator`)
ejecuta los pasos en orden topológico simple (transcript → {summary,
clinical_flags} → missing_information → anamnesis), de forma síncrona,
sin colas ni workers. La arquitectura permite sustituirlo por un
orquestador que ejecute en paralelo los pasos sin dependencias cruzadas
entre sí (`summary` y `clinical_flags` son independientes entre ellos)
**sin modificar ningún `PipelineStep`** — el contrato de cada paso ya
expone sus dependencias, es el orquestador quien decide cómo
aprovecharlas. No se introducen colas, workers ni procesamiento
distribuido en esta fase.

---

## 2. Arquitectura

### 2.1 Principio rector (heredado, no nuevo)

Igual que el resto del backend (ver [architecture.md](architecture.md)
§2 y §4): `presentation → domain ← infrastructure`, con toda integración
externa detrás de una interfaz abstracta, seleccionada en tiempo de
ejecución, nunca importada directamente por el dominio.

### 2.2 Principios de seguridad que rigen todo el diseño

**Decisión cerrada.** Cinco principios, aplicados de forma transversal
en cada decisión de este documento:

- **Privacy by Design**: cada nueva tabla/columna se diseña asumiendo
  desde el primer día que podría contener datos sanitarios reales en el
  futuro (ver [privacy-and-security.md](privacy-and-security.md) §1).
- **Data Minimization**: ninguna tabla duplica contenido sensible que ya
  vive en otro sitio sin una razón explícita (§3.2 de este documento:
  `ai_generation_runs` no almacena texto salvo que se active
  explícitamente, §7.5).
- **Human in the Loop**: la IA nunca persiste directamente — todo pasa
  por `review_pending` antes de `approved` (§1.1).
- **Auditability**: toda generación queda trazada (proveedor, modelo,
  coste, tiempo, plantilla, versión — §7.6).
- **Provider Agnostic Architecture**: ningún módulo de dominio importa un
  SDK de proveedor concreto; todo pasa por las interfaces de §6.1.

### 2.3 Dos módulos

- **`ai_pipeline/`** (nuevo): dominio y orquestación específicos de este
  producto — entidades, máquina de estados, orquestador, renderizador de
  prompts, servicio de aplicación, API.
- **`integrations/`** (ya previsto en [architecture.md](architecture.md),
  ampliado): las interfaces de proveedor y sus `Mock*`.

### 2.4 Estructura de carpetas

```
backend/app/
  ai_pipeline/
    domain/
      entities.py                  # AIArtifact, AIArtifactVersion, AIGenerationRun,
                                    # AIPipelineRun, PipelineResult, enums (§4)
      artifact_repository.py        # Protocol
      generation_run_repository.py  # Protocol
      pipeline_run_repository.py    # Protocol
      prompt_template_repository.py # Protocol
      prompt_renderer.py             # PromptRenderer (interno, no en integrations/)
      pipeline.py                     # PipelineOrchestrator (Protocol) +
                                       # SequentialPipelineOrchestrator (implementación)
      steps/
        base.py                        # PipelineStep (Protocol)
        transcription_step.py
        summary_step.py
        clinical_flags_step.py
        missing_information_step.py
        anamnesis_step.py
    infrastructure/
      orm.py
      repository.py
    service.py                          # AIPipelineService: autoriza → ejecuta →
                                         # persiste → audita → commit
    api/
      schemas.py
      router.py
  integrations/
    domain/
      transcription_provider.py         # TranscriptionProvider
      language_model_provider.py         # LanguageModelProvider
      summary_generator.py                # SummaryGenerator
      anamnesis_generator.py               # AnamnesisGenerator
      clinical_flags_generator.py           # ClinicalFlagsGenerator
      missing_information_generator.py       # MissingInformationGenerator
      cost_estimator.py                       # CostEstimator
      token_counter.py                         # TokenCounter
    mocks/
      mock_transcription_provider.py
      mock_language_model_provider.py
      mock_summary_generator.py
      mock_anamnesis_generator.py
      mock_clinical_flags_generator.py
      mock_missing_information_generator.py
      mock_cost_estimator.py
      mock_token_counter.py
```

Mismo patrón de tres capas ya usado en `clinical_sessions/`: `domain/`
sin SQLAlchemy, `infrastructure/` con el ORM y los repositorios
concretos, `service.py` orquestando autorización + dominio + auditoría +
commit, `api/` con esquemas Pydantic separados del ORM.

`PromptRenderer` vive en `ai_pipeline/domain/`, no en `integrations/`: no
es un proveedor externo sustituible, es lógica interna — mismo criterio
ya aplicado a `AudioStorage`/`ClinicalFlagRuleset` en
[architecture.md](architecture.md) §11.

---

## 3. Modelo de datos (resumen — esquema completo en data-model.md)

### 3.1 `AIArtifact`: por qué una entidad genérica y no tablas independientes

**Decisión cerrada: modelo híbrido.** Registrado aquí el análisis
completo porque documenta el porqué de la decisión, no porque el esquema
en sí viva en este documento (ver [data-model.md](data-model.md) §10 para
las columnas exactas).

| | Tablas independientes (diseño anterior) | `AIArtifact` genérico (adoptado) |
|---|---|---|
| Ventaja | Columnas tipadas por artefacto | Un único mecanismo de versionado, estado y auditoría técnica reutilizado por los 5 pasos actuales y cualquier paso futuro, sin migración nueva |
| Ventaja | — | Encaja directamente con los campos de auditoría exigidos (proveedor/modelo/coste/tokens/tiempo): una sola tabla los captura una vez, no cinco veces |
| Inconveniente | Cada artefacto nuevo repite tabla + ORM + repositorio + versionado + auditoría técnica — cinco veces la misma ceremonia | Pierde validación de tipos a nivel de columna SQL — se compensa con un esquema Pydantic distinto por `artifact_type`, validado en `service.py` (mismo rigor que ya tenía la anamnesis con su `content` en JSONB en el diseño previo) |
| Inconveniente | Un sexto tipo de artefacto futuro exige migración de esquema nueva | Consultas por atributo específico de un tipo requieren JSON path o una proyección de lectura aparte (no necesaria hoy) |

El **sobre común** (`AIArtifact`) contiene: estado, versión vigente,
confianza, auditoría de aprobación/rechazo, timestamps. El **contenido
específico** (`AIArtifactVersion.content`) permanece desacoplado,
validado por un esquema propio de cada `artifact_type` — nunca se mezcla
la forma de una anamnesis con la de un resumen dentro del mismo esquema
de validación.

### 3.2 Tablas (ver data-model.md §10 para el detalle de columnas)

- `ai_artifacts` — un sobre por (sesión, tipo de artefacto).
- `ai_artifact_versions` — historial append-only; nunca se edita ni se
  borra una fila existente.
- `ai_generation_runs` — una fila por ejecución de un paso del pipeline;
  la auditoría técnica pedida (proveedor, modelo, latencia, tiempo de
  ejecución, tokens, coste, plantilla).
- `ai_pipeline_runs` — una fila por disparo completo del pipeline;
  agrupa los `ai_generation_runs` de una misma ejecución.
- `prompt_templates` — plantillas versionadas (§7.4).
- `consents` (tabla ya existente, ampliada con `consent_version` — §7.3).

### 3.3 Versionado

Cada generación exitosa o cada edición humana crea una fila nueva en
`ai_artifact_versions` con `version_number` incrementado; nunca se
modifica ni se borra una versión existente. `ai_artifacts.current_version_id`
avanza a la versión nueva. Las versiones anteriores siguen siendo
consultables (solo lectura). Solo la disposición de la **versión
vigente** importa para `ai_artifacts.status` — una versión antigua no
tiene estado de revisión propio, es historial.

---

## 4. Entidades

Pseudocódigo ilustrativo — no es código a implementar todavía. Mismo
estilo que `clinical_sessions/domain/entities.py` (dataclasses
`slots=True`, `StrEnum`).

```python
class AIArtifactType(StrEnum):
    TRANSCRIPT = "transcript"
    SUMMARY = "summary"
    CLINICAL_FLAGS = "clinical_flags"
    MISSING_INFORMATION = "missing_information"
    ANAMNESIS = "anamnesis"


class AIArtifactStatus(StrEnum):
    REVIEW_PENDING = "review_pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AIArtifactVersionSource(StrEnum):
    AI_GENERATED = "ai_generated"
    HUMAN_EDITED = "human_edited"


class AIGenerationRunStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AIPipelineRunStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIALLY_FAILED = "partially_failed"


@dataclass(slots=True)
class AIArtifact:
    id: uuid.UUID
    clinical_session_id: uuid.UUID
    artifact_type: AIArtifactType
    status: AIArtifactStatus
    current_version_id: uuid.UUID
    confidence: int | None          # 0-100; espejo desnormalizado de
                                     # current_version.confidence (§7.2)
    schema_version: int
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    rejected_by: uuid.UUID | None
    rejected_at: datetime | None
    rejection_reason: str | None
    deleted_by: uuid.UUID | None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class AIArtifactVersion:
    id: uuid.UUID
    ai_artifact_id: uuid.UUID
    version_number: int
    content: dict[str, Any]         # forma validada por artifact_type (§7.1)
    confidence: int | None          # 0-100; solo si source = ai_generated
    source_map: dict[str, Any] | None  # diseño, no poblado aún (§7.7)
    source: AIArtifactVersionSource
    generation_run_id: uuid.UUID | None
    created_by: uuid.UUID | None
    change_note: str | None
    created_at: datetime


@dataclass(slots=True)
class AIGenerationRun:
    id: uuid.UUID
    ai_pipeline_run_id: uuid.UUID
    clinical_session_id: uuid.UUID
    artifact_type: AIArtifactType
    ai_artifact_id: uuid.UUID | None
    resulting_version_number: int | None
    status: AIGenerationRunStatus
    provider_name: str
    model_name: str | None
    prompt_template_id: uuid.UUID | None
    prompt_template_version: int | None
    input_token_count: int | None
    output_token_count: int | None
    estimated_cost_usd: Decimal | None
    latency_ms: int | None           # duración de la llamada al provider
    execution_time_ms: int | None    # duración total del paso (incluye
                                      # render de prompt, parseo, persistencia)
    rendered_system_prompt: str | None  # solo si Settings.ai_store_rendered_prompts (§7.5)
    rendered_user_prompt: str | None    # idem
    raw_response: dict[str, Any] | None # idem
    started_at: datetime
    completed_at: datetime | None
    failure_reason: str | None
    request_id: str | None


@dataclass(slots=True)
class AIPipelineRun:
    id: uuid.UUID
    clinical_session_id: uuid.UUID
    triggered_by: uuid.UUID
    status: AIPipelineRunStatus
    started_at: datetime
    completed_at: datetime | None
    request_id: str | None


@dataclass(slots=True)
class PromptTemplate:
    id: uuid.UUID
    name: str
    version: int
    description: str | None
    system_prompt: str | None
    user_prompt_template: str
    variables_schema: dict[str, Any]
    is_active: bool
    created_by: uuid.UUID
    change_note: str | None
    created_at: datetime


@dataclass(slots=True)
class PipelineStepOutcome:
    """Resultado de un paso — no persistido, DTO en memoria."""
    artifact_type: AIArtifactType
    status: AIGenerationRunStatus | None   # None si el paso se saltó (§8)
    ai_artifact: AIArtifact | None
    generation_run: AIGenerationRun | None
    skipped_reason: str | None


@dataclass(slots=True)
class PipelineResult:
    """Devuelto por el orquestador; DTO calculado a partir de
    ai_pipeline_runs + ai_generation_runs + ai_artifacts — no es una tabla
    propia, evita duplicar auditoría en dos sitios."""
    pipeline_run: AIPipelineRun
    outcomes: list[PipelineStepOutcome]

    @property
    def total_estimated_cost_usd(self) -> Decimal: ...
    @property
    def total_execution_time_ms(self) -> int: ...
```

---

## 5. Responsabilidades

| Componente | Responsabilidad | No responsable de |
|---|---|---|
| `PipelineOrchestrator` | Decidir en qué orden ejecutar los pasos según sus dependencias declaradas, y qué hacer ante el fallo de uno (§8) | Generar contenido, validar permisos, persistir |
| `PipelineStep` (uno por tipo de artefacto) | Declarar `depends_on()`; invocar el provider correspondiente; medir latencia/tiempo de ejecución/tokens/coste; traducir la respuesta del proveedor a la forma canónica JSON de `content` (§7.1) | Decidir si el paso se ejecuta (eso es del orquestador), autorizar, hacer commit |
| `AIPipelineService` | Autorizar → invocar al orquestador → persistir artefactos/versiones/runs → escribir `audit_logs` → commit transaccional | Lógica de generación en sí (delegada en los providers vía los pasos) |
| `Provider`/`Generator` (`integrations/`) | Producir el contenido bruto (o, en el mock, determinista) | Persistencia, versionado, autorización, elección de prompt |
| `PromptRenderer` | Sustituir variables en una plantilla, validar que las requeridas están presentes, sanear el texto insertado (§9 riesgos, inyección de prompt) | Elegir qué plantilla usar (del `PipelineStep`) ni llamar al modelo |
| `CostEstimator` / `TokenCounter` | Estimar coste/tokens de forma aislada, reutilizable por cualquier paso | Facturación real, límites de gasto (extensión futura, no implementada) |
| `clinical_flags` (tabla existente, sin cambios) | Disposición por ítem (confirmar/descartar) tras generarse el artefacto `clinical_flags` | Auditoría técnica de la generación (vive en `ai_generation_runs`) |
| `consents` (tabla existente, ampliada) | Registro de consentimiento de procesamiento por IA, incluida su versión de política aceptada | Bloquear la generación en el MVP (§7.3: no forzado todavía) |

---

## 6. Interfaces

Todas como `Protocol`, igual que `ClinicalSessionRepository` y
`CurrentUserProvider` en el código actual. Cada una con una
implementación `Mock*`; ninguna implementación real todavía.

### 6.1 Proveedores de contenido (`integrations/domain/`)

> **Ampliación (Fase 5 — ver
> [development-plan.md](development-plan.md)).** `TranscriptionInput`
> gana un campo opcional `audio: AudioForTranscription | None` (bytes ya
> leídos de `AudioStorage`, nunca la referencia de almacenamiento) y
> `TranscriptionResult` gana `duration_ms: int | None` y
> `segments: list[TranscriptionSegment] | None` (diarización:
> `speaker`/`start_ms`/`end_ms`/`text`). `MockTranscriptionProvider`
> ignora `audio` por completo y nunca puebla los campos nuevos — el Mock
> Pipeline (`run_pipeline`) no cambia de comportamiento. Solo
> `AssemblyAITranscriptionProvider`, invocado exclusivamente desde
> `AIPipelineService.transcribe_from_audio` (nunca desde `run_pipeline`),
> recibe `audio` y puebla los campos nuevos — ver
> [transcription-benchmark.md](transcription-benchmark.md).

```python
class TranscriptionProvider(Protocol):
    async def transcribe(self, input: TranscriptionInput) -> TranscriptionResult: ...


class LanguageModelProvider(Protocol):
    """Interfaz de bajo nivel: una llamada de completado, sin conocer para
    qué artefacto se usa. Es la única interfaz que implementarían SDKs de
    proveedores reales (OpenAI, Anthropic, Gemini, Ollama...) — ningún otro
    Generator de este bloque se implementa directamente contra un SDK de
    proveedor, todos componen esta interfaz (ver §9.2)."""
    async def complete(
        self, prompt: RenderedPrompt, *, model: str | None = None
    ) -> LanguageModelResponse: ...


class SummaryGenerator(Protocol):
    async def generate(self, transcript: str, *, context: SessionContext) -> SummaryDraft: ...


class ClinicalFlagsGenerator(Protocol):
    """Sustituye y absorbe a la interfaz `ClinicalFlagRuleset` del diseño
    anterior (ver §12, inconsistencia resuelta): mismo propósito, nombre
    unificado con el resto de pasos del pipeline, firma actualizada al
    nuevo orden del grafo (§1.4) — ya no recibe `anamnesis_draft`, porque
    la anamnesis todavía no existe en este punto del pipeline.
    A diferencia de Summary/MissingInformation/Anamnesis, una
    implementación de esta interfaz **no está obligada** a componer
    `LanguageModelProvider`: el checklist de demostración
    (`MockClinicalFlagsGenerator`, heredero directo de
    `DemoClinicalFlagRuleset`) es deliberadamente **basado en reglas, sin
    LLM** — decisión de seguridad clínica ya cerrada en
    clinical-safety.md §7, que esta consolidación no revierte. Una futura
    implementación LLM-based sería igualmente válida contra esta misma
    interfaz, pero no es la elegida para el MVP."""
    async def generate(self, transcript: str, *, context: SessionContext) -> list[ClinicalFlagDraft]: ...


class MissingInformationGenerator(Protocol):
    """Depende del resumen y de las señales de alerta, no de la
    anamnesis — la anamnesis todavía no existe en este punto del pipeline
    (§1.3, §1.4)."""
    async def generate(
        self, summary: str, clinical_flags: list[ClinicalFlagDraft], *, context: SessionContext
    ) -> list[MissingInfoItem]: ...


class AnamnesisGenerator(Protocol):
    """Último paso del grafo: recibe tanto la transcripción (texto fuente)
    como la información ausente ya identificada, para producir un
    borrador consciente de sus propias lagunas."""
    async def generate(
        self,
        transcript: str,
        missing_information: list[MissingInfoItem],
        *,
        context: SessionContext,
    ) -> AnamnesisDraft: ...


class CostEstimator(Protocol):
    def estimate(
        self, *, provider: str, model: str | None, input_tokens: int, output_tokens: int
    ) -> Decimal: ...


class TokenCounter(Protocol):
    def count(self, text: str, *, model: str | None) -> int: ...
```

`SummaryGenerator`/`MissingInformationGenerator`/`AnamnesisGenerator`
**componen** un `LanguageModelProvider` + una `PromptTemplate`; no lo
sustituyen — ver §9.2. `ClinicalFlagsGenerator` es la excepción
deliberada: su implementación de referencia en el MVP
(`MockClinicalFlagsGenerator`) es un checklist basado en reglas, sin
`LanguageModelProvider` de por medio — ver la nota en §6.1.

### 6.2 Orquestación (`ai_pipeline/domain/`)

```python
class PipelineStep(Protocol):
    artifact_type: AIArtifactType

    def depends_on(self) -> frozenset[AIArtifactType]:
        """Qué otros artifact_type deben haberse completado antes de este
        paso (§1.4). Permite que un futuro orquestador paralelo decida el
        orden sin que el paso lo sepa."""
        ...

    async def run(self, context: PipelineExecutionContext) -> PipelineStepOutcome: ...


class PipelineOrchestrator(Protocol):
    async def run(
        self,
        clinical_session_id: uuid.UUID,
        triggered_by: uuid.UUID,
        steps: Sequence[PipelineStep],
    ) -> PipelineResult: ...


class PromptRenderer(Protocol):
    def render(self, template: PromptTemplate, variables: dict[str, Any]) -> RenderedPrompt: ...
```

### 6.3 Repositorios (`ai_pipeline/domain/`)

Mismo patrón que `ClinicalSessionRepository`: `Protocol` con métodos
`async` que reciben la `AsyncSession` explícitamente, filtrados siempre
por `clinic_id`/`clinical_session_id` según corresponda.

```python
class AIArtifactRepository(Protocol):
    async def get_by_session_and_type(
        self, session: AsyncSession, clinic_id: uuid.UUID,
        clinical_session_id: uuid.UUID, artifact_type: AIArtifactType,
    ) -> AIArtifact | None: ...

    async def add_version(
        self, session: AsyncSession, artifact: AIArtifact, version: AIArtifactVersion,
    ) -> AIArtifact: ...
    # crea (o reutiliza) el AIArtifact y añade una AIArtifactVersion nueva
    # en la misma operación (§3.3)

    async def update_disposition(
        self, session: AsyncSession, clinic_id: uuid.UUID, artifact_id: uuid.UUID,
        values: dict[str, Any],
    ) -> AIArtifact | None: ...
```

`AIGenerationRunRepository`, `AIPipelineRunRepository` y
`PromptTemplateRepository` siguen el mismo patrón CRUD mínimo que el
resto de repositorios del proyecto.

### 6.4 Mocks

Cada interfaz de §6.1 tiene una implementación `Mock*` determinista:
`MockTranscriptionProvider`, `MockLanguageModelProvider`,
`MockSummaryGenerator`, `MockClinicalFlagsGenerator`,
`MockMissingInformationGenerator`, `MockAnamnesisGenerator`,
`MockCostEstimator` (siempre devuelve `Decimal("0")`),
`MockTokenCounter` (heurística simple, sin dependencia externa). Todos
respetan desde el primer commit el lenguaje no diagnóstico de
[clinical-safety.md](clinical-safety.md) §2-3 y la regla de nunca marcar
un campo de anamnesis como `informado` sin cita de la transcripción.
`MockClinicalFlagsGenerator` es, específicamente, un checklist basado en
reglas (heredero directo de `DemoClinicalFlagRuleset` del diseño
anterior, ver §6.1) — no invoca `MockLanguageModelProvider`; sigue
etiquetado explícitamente como "no validado clínicamente, no apto para
uso con pacientes reales" en cada respuesta, sin cambios respecto a la
decisión ya cerrada en [clinical-safety.md](clinical-safety.md) §7.

---

## 7. Contratos

### 7.1 JSON First: el contrato interno nunca es texto libre

**Decisión cerrada.** Ningún artefacto expone texto libre ni Markdown
como contrato interno — todo `content` es JSON estructurado, incluidos
los artefactos que son "básicamente prosa":

| `artifact_type` | Forma de `content` |
|---|---|
| `transcript` | `{"text": str, "language": str}`, más `duration_ms: int` y `segments: [{"speaker": str \| null, "start_ms": int, "end_ms": int, "text": str}]` cuando el proveedor los aporta (Fase 5) — ambos ausentes con el Mock Pipeline, sin cambio de comportamiento |
| `summary` | `{"text": str}` |
| `clinical_flags` | `{"flags": [{"category": str, "description": str, "source_excerpt": str \| null, "ruleset_name": str}]}` |
| `missing_information` | `{"items": [{"topic": str, "suggested_question": str}]}` |
| `anamnesis` | Objeto con los 22 campos de [data-model.md](data-model.md) §3, cada uno `{"value": str, "status": "informado"\|"negado_explicitamente"\|"no_preguntado"\|"no_determinado"}` |

Incluso `summary`/`transcript` (prosa) se envuelven en un objeto JSON con
un campo `text`, nunca como una cadena suelta en la raíz de `content`.
Generar un PDF/documento/vista a partir de esto es responsabilidad de la
capa de presentación en el momento de exportar, no del contrato interno.

**Aclaración sobre el ejemplo del encargo.** El ejemplo ilustrativo
(`{"tinnitus": true, "vertigo": false, ...}`) usa booleanos para
ilustrar "JSON estructurado, no texto libre" como principio general. El
esquema real de `anamnesis` **mantiene el modelo de 4 estados por campo**
ya cerrado en [clinical-safety.md](clinical-safety.md) §6
(`informado`/`negado_explicitamente`/`no_preguntado`/`no_determinado`):
un booleano no puede representar "no se preguntó" sin colapsarlo a
`false`, que es exactamente el tipo de suposición prohibida por la regla
no negociable #4 de `CLAUDE.md` ("nunca inventes valores de anamnesis que
no estén en la transcripción"). El principio JSON First se cumple con la
estructura de 4 estados; no se sustituye por booleanos.

### 7.2 Por qué cada `*Generator` compone `LanguageModelProvider` en vez de sustituirlo

Dos ejes de sustitución independientes:

- **Eje del proveedor**: qué SDK/vendor genera el texto (`mock` hoy,
  `openai`/`anthropic`/... en el futuro) — cambia sin tocar ninguna
  lógica de negocio de resumen/flags/anamnesis.
- **Eje del artefacto**: cómo se interpreta y valida la salida cruda para
  producir el `content` canónico de cada tipo — cambia sin tocar qué
  proveedor está activo.

Si `AnamnesisGenerator` implementara directamente contra un SDK de
proveedor, cambiar de proveedor obligaría a reimplementar el
parseo/validación de anamnesis para cada proveedor nuevo — el
acoplamiento que la regla no negociable #6 de `CLAUDE.md` prohíbe. Con la
composición, un `AnamnesisGenerator` concreto recibe un
`LanguageModelProvider` inyectado y es agnóstico de cuál sea
(*Provider Agnostic Architecture*, §2.2).

### 7.3 Consentimiento

**Decisión cerrada.** Se amplía la tabla `consents` ya existente
([data-model.md](data-model.md) §2) con `consent_version` (identifica
qué versión de la política de consentimiento se aceptó). No se crea una
estructura paralela: `ai_processing_consent` se representa como una fila
de `consents` con `consent_type = procesamiento_ia`, `granted = true`,
`consent_version` y `recorded_at` (ya existente, cumple el rol de
`consent_timestamp`).

`AIPipelineService.run_pipeline` incluye, desde esta fase, el punto de
extensión donde se comprobaría el consentimiento — **en el MVP no
bloquea**: si no existe un registro, se asume `true` implícitamente
(comportamiento idéntico al actual, sin cambios de conducta). El día que
el consentimiento deba exigirse explícitamente, este mismo punto pasa a
lanzar `ConflictError` si no hay un `consents` con `granted = true` y la
`consent_version` vigente — sin rediseñar nada, solo activando una
comprobación ya prevista.

### 7.4 Gestión de prompts

**Decisión cerrada.** Arquitectura de origen dual:

```
Repositorio Git (/backend/app/ai_pipeline/prompts/*.md, revisable en PR)
      │
      ▼
   Seed (arranque/script de seed)
      │
      ▼
Base de datos (prompt_templates — fuente de verdad en ejecución)
      │
      ▼
  Uso por el Pipeline
```

- El repositorio Git es la fuente **inicial**: cada plantilla nace como
  un fichero versionado en `ai_pipeline/prompts/`, revisable como
  cualquier otro cambio de comportamiento (relevante para
  [clinical-safety.md](clinical-safety.md)).
- El seed puebla `prompt_templates` a partir de esos ficheros si no existe
  ya una versión activa con ese `name`.
- A partir de ahí, la base de datos es la fuente de verdad en tiempo de
  ejecución — permite evolucionar prompts sin desplegar.
- Cada plantilla incluye: `name`, `version`, `description`,
  `variables_schema`, `system_prompt`, `user_prompt_template`.
- Publicar una plantilla nueva = insertar una fila nueva con `version`
  incrementado y `is_active = true`; la anterior pasa a `is_active =
  false` pero se conserva íntegra (append-only).
- El contenido no confiable (transcripción) solo puede ocupar variables
  declaradas del `user_prompt_template`, nunca el `system_prompt` — ver
  §9 (riesgos, inyección de prompt).
- Cada `ai_generation_runs` fija `prompt_template_id` +
  `prompt_template_version` **copiados en el momento de la ejecución**
  (no una referencia "viva"): si la plantilla se republica después, la
  fila histórica sigue señalando la versión realmente usada.

### 7.5 Prompt renderizado: almacenamiento configurable

**Decisión cerrada.** Se soporta guardar el prompt completamente
renderizado (con variables ya sustituidas) y la respuesta cruda del
proveedor, pero de forma **configurable y desactivada por defecto**:

- Nueva variable de configuración (`core/config.py`, mismo patrón que el
  resto de `Settings`): `ai_store_rendered_prompts: bool = False`.
- Cuando es `false` (por defecto, incluida producción salvo activación
  explícita): `ai_generation_runs.rendered_system_prompt`,
  `rendered_user_prompt` y `raw_response` son siempre `NULL`, sin
  excepción.
- Cuando es `true`: esas tres columnas se rellenan en cada ejecución,
  permitiendo depuración y reproducibilidad exacta.
- **Nunca**, en ningún caso, se almacena una clave de API ni ningún otro
  secreto en estas columnas — las credenciales de proveedor son
  cabeceras de transporte/autenticación, nunca parte del contenido del
  prompt.

**Implicaciones de privacidad (documentadas explícitamente, como exige
esta decisión).** El prompt renderizado y la respuesta cruda contienen el
mismo contenido clínico-adyacente que ya vive, de forma versionada, en
`ai_artifact_versions.content` (transcripción, resúmenes, anamnesis).
Activar este almacenamiento **duplica** esa superficie de exposición en
una segunda tabla — la razón por la que el valor por defecto es `false`:
minimización de datos ([privacy-and-security.md](privacy-and-security.md)
§2). Si se activa, estas columnas deben añadirse a la lista de columnas
candidatas a cifrado a nivel de aplicación de
[privacy-and-security.md](privacy-and-security.md) §4, igual que
`ai_artifact_versions.content`. Activar esta opción es una decisión que
debe tomarse de forma explícita y documentada por entorno, nunca por
defecto.

### 7.6 Auditoría técnica

**Decisión cerrada.** `ai_generation_runs` (ver columnas exactas en
[data-model.md](data-model.md) §10) guarda: `provider_name`,
`model_name`, `latency_ms` (duración de la llamada al proveedor),
`execution_time_ms` (duración total del paso, incluye render de prompt,
parseo y persistencia — puede ser mayor que `latency_ms`),
`input_token_count`/`output_token_count`, `estimated_cost_usd`,
`resulting_version_number` (qué versión de `ai_artifact_versions`
produjo), `prompt_template_id`/`prompt_template_version`.

**Nunca guarda**: secretos, claves de API, ni (salvo activación explícita
de §7.5) el contenido del prompt o de la respuesta. Esta distinción es
intencional y se documenta aquí de forma explícita: `ai_generation_runs`
es una tabla de **telemetría técnica**, no una copia del contenido
clínico-adyacente generado — ese vive, versionado, en
`ai_artifact_versions.content`.

### 7.7 Source mapping (diseño — no implementado)

**Decisión cerrada sobre el diseño, implementación fuera de esta fase.**
Cada fragmento generado debe poder asociarse a su origen: segmento de
audio, rango de transcripción, timestamps, offsets — para que un
audioprotesista pueda saber exactamente de dónde procede cualquier frase
generada.

Diseño: `AIArtifactVersion.source_map` (JSONB, nullable), estructurado
como un mapa desde cada "ruta" del `content` hacia su origen:

```json
{
  "tinnitus": {
    "transcript_range": {"start_offset": 450, "end_offset": 512},
    "audio_segment": {"start_ms": 34200, "end_ms": 36100}
  }
}
```

Para artefactos de texto único (`summary`, `transcript`) sería una lista
de pares de alineación en vez de un mapa por campo. Depende de que el
futuro `TranscriptionProvider` real produzca offsets/timestamps —
`MockTranscriptionProvider` no está obligado a poblarlo con datos reales;
puede dejarlo vacío o con offsets ficticios de la propia fixture. No se
implementa la población de este campo en el backlog de esta fase (ver
[development-plan.md](development-plan.md) Fase 4) — se deja el campo
listo para cuando exista una fuente real de esos datos.

---

## 8. Secuencia del pipeline

Ejecución de `POST /clinical-sessions/{id}/ai/generate`:

1. `AIPipelineService.run_pipeline(current_user, clinical_session_id, request_id)`.
2. Autoriza (`authorize_ai_pipeline_action(current_user, AIPipelineAction.TRIGGER)`)
   y resuelve la sesión (404 si no existe o es de otra clínica).
3. Comprueba que no exista ya un `ai_pipeline_runs` en `queued`/`processing`
   para la misma sesión (`ConflictError` → 409 si lo hay — un pipeline
   activo a la vez por sesión).
4. Comprueba (informativamente, sin bloquear en el MVP, §7.3) el
   consentimiento de procesamiento por IA del paciente.
5. Crea `AIPipelineRun` (`status = processing`, `started_at = now()`).
6. Ejecuta los pasos en orden topológico (`transcript` → `{summary,
   clinical_flags}` → `missing_information` → `anamnesis`):
   a. Si alguna dependencia de `step.depends_on()` falló o se saltó en
      esta misma ejecución → el paso se **salta**
      (`skipped_reason` poblado, **no** se crea fila en
      `ai_generation_runs` — un paso nunca intentado no es lo mismo que
      uno que falló).
   b. En caso contrario: crea `AIGenerationRun` (`queued` → `processing`),
      resuelve la `PromptTemplate` activa si aplica, renderiza el prompt,
      invoca al provider, mide `latency_ms`/`execution_time_ms`/tokens/coste.
   c. Éxito: crea (o versiona) el `AIArtifact` vía
      `AIArtifactRepository.add_version` con su `confidence`; `status =
      completed`; si `artifact_type = clinical_flags`, además vuelca cada
      ítem de `content.flags` a una fila nueva de `clinical_flags` en
      `sugerida_ia`.
   d. Fallo: `status = failed` con `failure_reason`; el `AIArtifact`
      existente (si lo había) **no se toca**.
7. `AIPipelineRun.status` = `completed` si todos completaron,
   `partially_failed` si alguno falló/se saltó pero al menos uno
   completó, `failed` si ninguno completó.
8. Escribe una entrada en `audit_logs` (`ai_pipeline.triggered`, con
   `metadata = {"outcomes": {artifact_type: status}}` — solo nombres de
   tipo y estado, nunca contenido).
9. Commit único de toda la transacción — mismo principio que
   `ClinicalSessionService` (todo o nada).
10. Devuelve `PipelineResult`, serializado con el `ai_disclaimer`
    obligatorio por cada artefacto generado.

Aprobar/rechazar/editar sigue el patrón ya usado en
`ClinicalSessionService`: autoriza → valida (¿existe el artefacto? ¿la
versión vigente sigue en `review_pending`?) → opera → audita
(`ai_artifact.approved`/`ai_artifact.rejected`/`ai_artifact.edited`) →
commit. Editar crea una `AIArtifactVersion` (`source = human_edited`,
`confidence = null`) y devuelve `status` a `review_pending` si venía de
`approved` o `rejected`.

**`confidence` nunca decide nada por sí solo**: no existe ninguna ruta de
código en la que un valor de `confidence` alto provoque una aprobación
automática. Solo se usa para resaltar en la interfaz qué elementos
merecen especial atención en la revisión humana.

---

## 9. Diagrama textual

### 9.1 Arquitectura

```
┌───────────────────────────────────────────────────────────────────┐
│ ai_pipeline/api/router.py                                         │
│   POST   /clinical-sessions/{id}/ai/generate                      │
│   GET    /clinical-sessions/{id}/ai/artifacts/{type}               │
│   GET    /clinical-sessions/{id}/ai/artifacts/{type}/versions       │
│   PUT    /clinical-sessions/{id}/ai/artifacts/{type}                 │
│   POST   /clinical-sessions/{id}/ai/artifacts/{type}/approve          │
│   POST   /clinical-sessions/{id}/ai/artifacts/{type}/reject            │
│   GET    /clinical-sessions/{id}/ai/pipeline-runs/{run_id}              │
└───────────────────────────┬───────────────────────────────────────┘
                             ▼
┌───────────────────────────────────────────────────────────────────┐
│ ai_pipeline/service.py — AIPipelineService                        │
│   autoriza → orquesta → persiste → audita → commit                │
└───────────────────────────┬───────────────────────────────────────┘
                             ▼
┌───────────────────────────────────────────────────────────────────┐
│ ai_pipeline/domain/pipeline.py — PipelineOrchestrator              │
│   SequentialPipelineOrchestrator (síncrono, orden topológico)     │
└──────┬─────────────────────────┬──────────────┬───────────────────┘
       ▼                         ▼              (según depends_on)
 TranscriptionStep      SummaryStep / ClinicalFlagsStep
       │                         │
       │                         ▼
       │              MissingInformationStep
       │                         │
       │                         ▼
       │                  AnamnesisStep
       ▼                         ▼
┌───────────────────────────────────────────────────────────────────┐
│ integrations/domain/  (Protocols)                                 │
│   TranscriptionProvider   LanguageModelProvider                   │
│   SummaryGenerator   ClinicalFlagsGenerator                        │
│   MissingInformationGenerator   AnamnesisGenerator                  │
│   CostEstimator   TokenCounter                                       │
└───────────────────────────┬───────────────────────────────────────┘
                             ▼
┌───────────────────────────────────────────────────────────────────┐
│ integrations/mocks/  (única implementación en esta fase)          │
│   Mock*  — deterministas, sin red, sin coste real                 │
└───────────────────────────────────────────────────────────────────┘

                     (en paralelo, sin acoplarse al pipeline)
┌───────────────────────────────────────────────────────────────────┐
│ ai_pipeline/domain/prompt_renderer.py — PromptRenderer            │
│   lee prompt_templates (versionadas) → RenderedPrompt              │
└───────────────────────────────────────────────────────────────────┘
```

### 9.2 Dos ejes de estado

```
Eje de EJECUCIÓN (por paso, ai_generation_runs.status):

  queued ──▶ processing ──┬──▶ completed
                           └──▶ failed

Eje de DISPOSICIÓN (por artefacto, ai_artifacts.status):

              ┌──────────────────────────────┐
              ▼                              │
  review_pending ──▶ approved ───────────────┤ (editar tras aprobar)
              │                              │
              └──▶ rejected ─────────────────┘ (editar/regenerar tras rechazar)
```

Ambos ejes son independientes: un artefacto puede estar `approved`
mientras su próxima regeneración está `processing` — la regeneración en
curso no invalida la versión aprobada vigente hasta que complete con
éxito. **`created` no es necesario** (un `ai_generation_runs` nace
directamente en `queued`, no hay hueco intermedio en este MVP
síncrono). **`versioned` no es un estado** (es un hecho estructural: todo
`AIArtifact` tiene ≥1 versión desde que existe, igual que
`clinical_sessions` no tiene un estado "ha sido creada").

---

## 10. Backlog

Ver [development-plan.md](development-plan.md) Fase 4 para el desglose
completo de subfases (4.1-4.8) con criterios de aceptación — no se
duplica aquí para evitar mantener dos listas del mismo backlog.

---

## 11. Riesgos

| Riesgo | Mitigación |
|---|---|
| Sin validación de tipos a nivel SQL, un `content` mal formado podría persistirse | Validación Pydantic por `artifact_type` en la capa de servicio antes de persistir (§3.1, §7.1) |
| Inyección de prompt: el texto de la transcripción se inserta en un prompt destinado a un LLM | Solo puede ocupar variables declaradas del `user_prompt_template`, nunca el `system_prompt` (§7.4) |
| Fuga del payload de un proveedor real hacia `ai_generation_runs` | Por diseño no se almacena, salvo activación explícita y documentada (§7.5) |
| Filtración de secretos de proveedor (API keys) | Exclusivamente variables de entorno; nunca en `prompt_templates`, `ai_generation_runs` ni `audit_logs` (§7.6) |
| Uso indebido de `confidence` para aprobar automáticamente | Prohibido estructuralmente: ninguna ruta de código condiciona una transición a `approved` por el valor de `confidence` (§8) |
| Gasto descontrolado al activar un proveedor de pago real | `CostEstimator` como punto de extensión ya preparado para un guardarraíl de coste máximo configurable — no implementado en el MVP |
| Generalizar en exceso: un futuro artefacto de forma muy distinta (p. ej. salida binaria) no encajaría en `content: JSONB` | `content` se mantiene deliberadamente flexible; un artefacto binario sería una extensión explícita, no forzada en este modelo |
| Envío de datos clínicos reales a un tercero sin acuerdo de tratamiento de datos | Bloqueo estructural mientras tanto (solo `Mock*` disponibles); activar un proveedor real es una decisión de producto/legal explícita y posterior |
| Consentimiento no forzado en el MVP (§7.3) | Aceptado conscientemente para el MVP con datos ficticios; el punto de extensión ya existe para activarlo sin rediseño cuando corresponda |
| Ambigüedad en fallos parciales del pipeline | Distinción explícita `failed` (se intentó y falló) vs `skipped` (no se intentó por dependencia fallida) — nunca mezclados (§8) |

---

## 12. Decisiones cerradas (2026-08-10)

Todas las decisiones de este documento tienen el mismo estatus que
cualquier "decisión cerrada" de [product-requirements.md](product-requirements.md).
Se enumeran aquí como referencia rápida; el detalle y la justificación
de cada una están en la sección correspondiente enlazada.

1. **Naming**: `TranscriptionProvider` (no `TranscriptProvider`),
   consistente con `SummaryGenerator`/`ClinicalFlagsGenerator`/
   `MissingInformationGenerator`/`AnamnesisGenerator`.
   `LanguageModelProvider` es la abstracción de bajo nivel que todos
   ellos componen — ver §6.1, §7.2.
2. **`AIArtifact`/`AIArtifactVersion`** en modelo híbrido — ver §3.1.
   `clinical_flags` sigue siendo una proyección especializada por ítem,
   no un documento genérico — ver §1.2.
3. **El pipeline es un grafo de dependencias**, no una cadena lineal —
   ver §1.4. Orquestador síncrono en esta fase; la arquitectura permite
   sustituirlo por uno paralelo sin tocar los pasos.
4. **Todos los providers con Mock**; ningún proveedor real (OpenAI,
   Anthropic, Claude, Gemini, Ollama, Whisper, Azure, AWS) ni API externa
   en esta fase — ver §6.4.
5. **Prompt management**: origen dual, Git → seed → base de datos — ver §7.4.
6. **Prompt renderizado**: almacenamiento configurable
   (`ai_store_rendered_prompts`, `false` por defecto), nunca secretos —
   ver §7.5.
7. **Consentimiento**: se amplía `consents` con `consent_version`; no
   bloquea en el MVP, punto de extensión ya presente — ver §7.3.
8. **Concurrencia**: orquestador síncrono, sin colas/Celery/Redis/workers
   en esta fase; un `ai_pipeline_run` activo por sesión a la vez — ver §8.
9. **`confidence` (0-100)** en todo `AIArtifact`/`AIArtifactVersion`,
   nunca usado para aprobación automática — ver §4, §8.
10. **Source mapping**: diseño del campo `source_map`, sin implementar la
    población todavía — ver §7.7.
11. **JSON First**: contrato interno siempre JSON estructurado, nunca
    texto libre ni Markdown — ver §7.1.
12. **Estados en dos ejes independientes** (ejecución vs. disposición
    humana); sin `created` ni `versioned` como estados — ver §9.2.
13. **Auditoría en `ai_generation_runs`**: campos exactos exigidos,
    nunca secretos — ver §7.6.
14. **Seguridad**: Privacy by Design, Data Minimization, Human in the
    Loop, Auditability, Provider Agnostic Architecture — ver §2.2. La IA
    nunca persiste directamente (`AI → Draft → Human Review → Approve →
    Persist`, nunca `AI → Database`) — ver §1.1.

Decisiones adicionales, cerradas por extensión del patrón ya usado en
`clinical_sessions` (no señaladas explícitamente en el encargo, resueltas
aquí para no dejar nada pendiente antes de implementar — ver también el
resumen de cambios entregado junto con este documento):

15. **Matriz de permisos de `AIArtifactAction`/`AIPipelineAction`**:
    mismo patrón que `ClinicalSessionAction` — `admin` sin restricción;
    `audiologist` puede disparar el pipeline y aprobar/rechazar/editar
    únicamente sobre sesiones propias (`professional_id ==
    current_user.id`); `viewer` solo lectura. Sin rol de "revisor" nuevo
    en esta fase.
16. **Nivel de detalle en `audit_logs`**: una entrada agregada por
    ejecución completa (`ai_pipeline.triggered`) más una entrada por cada
    acción de disposición humana (`ai_artifact.approved`/`.rejected`/`.edited`)
    — no una entrada por cada paso individual del pipeline, ya cubierto
    con el detalle técnico completo en `ai_generation_runs`.
17. **`rejected` no es un estado terminal explícito**: un artefacto
    rechazado siempre puede reabrirse mediante edición manual o
    regeneración, igual que `approved → review_pending` al editar. No se
    introduce un estado "descartado permanentemente" en esta fase.
18. **`ClinicalFlagsGenerator` sustituye y absorbe a `ClinicalFlagRuleset`**
    (inconsistencia detectada durante la consolidación, no señalada en el
    encargo): el diseño previo de
    [clinical-safety.md](clinical-safety.md) §7 y
    [architecture.md](architecture.md) §4 definía `ClinicalFlagRuleset`
    con la firma `evaluate(transcript, anamnesis_draft)` — incompatible
    con el nuevo grafo de dependencias (§1.4), donde la anamnesis se
    genera la última y no existe todavía cuando se detectan señales de
    alerta. Se unifica bajo el nombre `ClinicalFlagsGenerator`
    (consistente con el resto de pasos del pipeline, sin dos nombres para
    el mismo concepto), con la firma nueva `generate(transcript,
    *, context)`. La implementación de referencia sigue siendo un
    checklist basado en reglas, **sin LLM** — no se reabre ni se revierte
    la decisión clínica ya cerrada de mantenerlo así (ver §6.1, §6.4).
    `DemoClinicalFlagRuleset` pasa a llamarse `MockClinicalFlagsGenerator`,
    mismo comportamiento y mismas salvaguardas clínicas.

---

## 13. Preguntas abiertas

Ninguna. Todas las preguntas planteadas en la versión anterior de este
documento han quedado resueltas por las decisiones de §12 (las 14
explícitas del encargo, más las 3 cerradas por extensión del patrón
existente, señaladas como tal en los puntos 15-17). No quedan decisiones
de arquitectura pendientes para empezar la Fase 4.1.

---

## 14. Criterios de aceptación

Por subfase — ver desglose y dependencias completas en
[development-plan.md](development-plan.md) Fase 4.

- **4.1 (dominio)**: los tests de dominio (transiciones de estado,
  invariantes de versionado, `depends_on()` de cada paso) pasan sin
  ninguna dependencia de SQLAlchemy, FastAPI ni ningún proveedor
  concreto.
- **4.2 (persistencia)**: migración desde base vacía funciona; existen
  los índices/`UNIQUE` de [data-model.md](data-model.md) §11; `consents`
  incluye `consent_version`; ningún `Mock*` ni endpoint todavía.
- **4.3 (mocks)**: cada `Mock*` tiene tests que verifican determinismo y
  ausencia de llamadas de red; tests de que ningún `Mock*Generator`
  produce lenguaje prohibido ni marca un campo de anamnesis `informado`
  sin evidencia.
- **4.4 (orquestador)**: disparar el pipeline sobre una sesión ficticia
  respeta el orden del grafo de §1.4; un fallo en `summary` no impide que
  `clinical_flags` se ejecute (dependencias independientes); un fallo en
  `missing_information` provoca que `anamnesis` se salte (`skipped`, no
  `failed`); cada `ai_generation_runs` tiene
  `provider_name`/`latency_ms`/`execution_time_ms`/`estimated_cost_usd`/
  tokens poblados.
- **4.5 (API)**: los endpoints de §9.1 responden según los contratos de
  §7; `403`/`404`/`409` se comportan igual que en `clinical_sessions`; un
  segundo disparo mientras hay un `ai_pipeline_run` en curso devuelve 409.
- **4.6 (prompts)**: existe al menos una plantilla activa por
  `artifact_type` que la usa, sembrada desde `/ai_pipeline/prompts/`;
  regenerar tras publicar una plantilla nueva usa la nueva versión;
  `ai_generation_runs` de ejecuciones anteriores sigue apuntando a la
  versión que realmente usaron; con `ai_store_rendered_prompts=false`
  (valor por defecto) las columnas de prompt renderizado son siempre
  `NULL`.
- **4.7 (exportación)**: ver [development-plan.md](development-plan.md)
  Fase 6.
- **4.8 (frontend)**: desde la UI se puede disparar el pipeline, ver cada
  artefacto con su aviso de IA y su `confidence`, ver el historial de
  versiones, y aprobar/rechazar/editar — todo con datos ficticios, sin
  audio real.

Constante en todas las subfases: no se implementa ningún proveedor real,
subida de audio, micrófono, almacenamiento definitivo de audio ni
transcripción real.
