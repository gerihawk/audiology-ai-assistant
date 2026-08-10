# Benchmark de proveedores de transcripción — Fase 5 / 5.1 / 5.2 / 5.3

Plataforma permanente para comparar proveedores de transcripción
(AssemblyAI, Deepgram, OpenAI, Speechmatics, Azure Speech, Google Speech,
AWS Transcribe, Whisper local...) usando exactamente los mismos audios.
Ver [development-plan.md](development-plan.md) Fase 5 para el criterio de
aceptación completo y [architecture.md](architecture.md) para el resto de
la arquitectura del backend.

**Fase 5** construyó la plataforma (audio real, `AssemblyAITranscriptionProvider`,
CLI de benchmark, JSON normalizado). **Fase 5.1** la convierte en una
herramienta de evaluación científica y reproducible: golden dataset con
transcripción de referencia, WER, métricas específicas de audiología
(terminología, negaciones, lateralidad), métricas de diarización, coste
real estimado (no Mock) y una herramienta de comparación entre
proveedores. **Fase 5.2** investiga si el fallo de diarización observado
en la primera prueba real (§19) se puede resolver con una configuración
mejor de AssemblyAI, mediante dos perfiles comparables
(`assemblyai_baseline`/`assemblyai_optimized`) sobre el mismo audio —
conclusión: mejora parcial, insuficiente (~83% del diálogo sigue
fusionado en un solo speaker), a más del doble de coste. **Fase 5.3**
integra un segundo proveedor real, Deepgram Nova-3 (§20), como candidato
a resolver la diarización que AssemblyAI no resuelve. Este documento
cubre las cuatro fases.

> **Corrección importante (Fase 5.2).** La primera prueba real
> (`consulta_ficticia_01`, informe de la sesión anterior) **sí** se grabó
> con dos personas distintas — una interpretando al audioprotesista, otra
> al paciente. El fallo de diarización observado (un único speaker
> detectado para toda la conversación, pese a `speaker_labels=True`) es
> por tanto un **fallo real de AssemblyAI para este audio**, no un
> artefacto de que una misma voz interpretara ambos papeles. Cualquier
> referencia anterior en este documento que sugiriera lo segundo queda
> corregida por esta nota — ver §19 para el experimento que investiga si
> una configuración distinta lo resuelve.

## 1. Qué NO es esta fase

- No integra ningún LLM (Summary/ClinicalFlags/MissingInformation/Anamnesis
  siguen siendo Mock, sin cambios).
- No implementa OpenAI/Speechmatics/Azure/Google/AWS/Whisper — solo
  `mock`, `assemblyai` y, desde la Fase 5.3, `deepgram` (§20). Añadir los
  restantes es extender el registro descrito en §3, no rediseñar nada.
- No genera HTML ni dashboards — solo JSON y tablas por terminal.
- No implementa NLP clínico para negaciones/lateralidad — comparación de
  texto contra patrones explícitos declarados en `metadata.json` (§7-8).
- No implementa DER (Diarization Error Rate) académico completo — una
  métrica de atribución de hablante interpretable y testeable (§9), sin
  usar timestamps (opcionales en la referencia).
- No genera ruido de fondo sintético para el dataset — los audios con
  ruido (`environment: office_noise`, etc.) deben grabarse así, no
  simularse (§13).

## 2. Arquitectura

Tres piezas, deliberadamente independientes entre sí salvo por el
contrato compartido:

```
app/integrations/                          benchmark/
  domain/                                     dataset.py         → DatasetCase, load_dataset_case
    transcription_provider.py                 reference.py         → Reference, load_reference
      TranscriptionProvider (Protocol)        dataset_metadata.py    → DatasetMetadata, load_metadata
      TranscriptionResult (+ model_name,      metrics/
        provider_metadata desde Fase 5.1)       text_normalize.py    → normalize_text/normalize_words
    audio_cost_estimator.py                     alignment.py          → align_words (Levenshtein)
      AudioCostEstimator (Protocol)              wer.py                 → compute_wer
      CostEstimate / CostEstimateSource            terminology.py        → evaluate_terminology
  mocks/                                           negation.py            → evaluate_negations
    mock_transcription_provider.py                  laterality.py          → evaluate_laterality
    mock_audio_cost_estimator.py                      diarization.py        → evaluate_diarization
  providers/                                    runner.py    → BenchmarkRunner
    assemblyai_transcription_provider.py        report.py    → build_report / write_report
    pricing_table_audio_cost_estimator.py       cli.py       → python -m benchmark.cli
  pricing.py  → tabla de precios centralizada   compare.py   → python -m benchmark.compare
  factory.py  → build_transcription_provider(settings, name=None)
              → build_audio_cost_estimator(settings, name=None)
```

`benchmark/` **no depende de `app/ai_pipeline/`**: no toca la base de
datos, no crea `AIArtifact`, no requiere una sesión clínica real ni un
`clinical_session_id` verdadero (usa uno aleatorio, opaco, exigido por el
contrato pero nunca persistido). Solo depende de `app/integrations/` — el
mismo contrato `TranscriptionProvider` que usa el AI Pipeline real (ver
§6), para que "comparar proveedores" y "usar un proveedor en producción"
sean exactamente la misma abstracción, nunca dos implementaciones
paralelas que puedan divergir. `benchmark/metrics/` tampoco depende de
`app/`: son funciones puras sobre texto, reutilizables fuera de este
proyecto si hiciera falta.

`app/integrations/factory.py` expone dos registros equivalentes en
diseño:

- `TRANSCRIPTION_PROVIDER_FACTORIES` — `build_transcription_provider(settings, name=None)`.
- `AUDIO_COST_ESTIMATOR_FACTORIES` — `build_audio_cost_estimator(settings, name=None)`.

Ambos siguen el mismo patrón: sin `name`, resuelven el proveedor activo
de la app (`TRANSCRIPTION_PROVIDER`); con `name`, `benchmark/` construye
la instancia que necesite para cada `--providers` pedido, sin tocar la
configuración global.

## 3. Cómo añadir un proveedor nuevo

Dos cambios, ambos en `app/integrations/`. El ejemplo de Deepgram de
abajo ya está implementado (Fase 5.3, ver §20) — se deja como referencia
concreta de los pasos para el siguiente proveedor (OpenAI, Speechmatics...).

```python
# factory.py
TRANSCRIPTION_PROVIDER_FACTORIES: dict[str, Callable[[Settings], TranscriptionProvider]] = {
    "mock": lambda settings: MockTranscriptionProvider(),
    "assemblyai": lambda settings: AssemblyAITranscriptionProvider(...),
    "deepgram": lambda settings: DeepgramTranscriptionProvider(
        api_key=settings.deepgram_api_key,
        ...
    ),
}

AUDIO_COST_ESTIMATOR_FACTORIES: dict[str, Callable[[Settings], AudioCostEstimator]] = {
    "mock": lambda settings: MockAudioCostEstimator(),
    "assemblyai": lambda settings: PricingTableAudioCostEstimator(settings),
    "deepgram": lambda settings: PricingTableAudioCostEstimator(settings),  # si Deepgram tampoco devuelve coste
}
```

Pasos completos:

1. Implementar `app/integrations/providers/deepgram_transcription_provider.py`
   con una clase que satisfaga `TranscriptionProvider` (`async def
   transcribe(self, input: TranscriptionInput) -> TranscriptionResult`),
   devolviendo siempre el contrato normalizado (§4), incluidos
   `model_name`/`provider_metadata` si la API los expone (§10).
2. Añadir la configuración necesaria a `Settings`
   (`app/core/config.py`) — solo variables de entorno, nunca
   credenciales hardcodeadas (regla no negociable #5 de `CLAUDE.md`).
   Documentar la variable en `.env.example` con un placeholder, nunca un
   valor real.
3. Si el proveedor no devuelve coste en su respuesta, añadir su precio a
   `app/integrations/pricing.py` (§11) — nunca hardcodeado en el
   `*CostEstimator` ni disperso por el código.
4. Añadir las entradas a los dos registros de arriba.
5. Añadir `"deepgram"` a la lista de valores válidos de
   `TRANSCRIPTION_PROVIDER` en `Settings` (`Literal[...]`) si se quiere
   activar como proveedor de producción del pipeline, no solo de
   benchmark.
6. Tests con HTTP mockeado (nunca llamadas reales, ver §14) — mismo
   patrón que `tests/test_assemblyai_provider.py`.

**Ningún otro módulo cambia**: ni `ai_pipeline/`, ni `audio/`, ni
`benchmark/runner.py`/`report.py`/`cli.py`/`compare.py`, ni las métricas
en `benchmark/metrics/`, ni la API. Ese es el criterio de aceptación
arquitectónico de esta fase.

## 4. Contrato normalizado

Todo `TranscriptionProvider` devuelve exactamente esta forma
(`app/integrations/domain/transcription_provider.py`):

```python
@dataclass(slots=True, frozen=True)
class TranscriptionSegment:
    speaker: str | None
    start_ms: int
    end_ms: int
    text: str

@dataclass(slots=True, frozen=True)
class TranscriptionResult:
    text: str
    language: str
    confidence: int | None = None       # 0-100
    duration_ms: int | None = None
    segments: list[TranscriptionSegment] | None = None
    model_name: str | None = None                    # Fase 5.1 — ver §10
    provider_metadata: dict[str, Any] | None = None    # Fase 5.1 — ver §10
```

El resto del sistema (`ai_pipeline/`, `benchmark/`) nunca conoce el
formato específico de un proveedor concreto (JSON de AssemblyAI, de
Deepgram...) — cada `*TranscriptionProvider` es responsable de traducir
la respuesta cruda de su API a este contrato antes de devolverla. Ver
también `docs/ai-pipeline-architecture.md` §7.1 (tabla de `content` por
`artifact_type`, incluida la extensión de `transcript` con
`duration_ms`/`segments`).

`TranscriptionInput.audio` (`AudioForTranscription`) lleva los bytes ya
leídos de `AudioStorage` — ningún `TranscriptionProvider` conoce
`AudioStorage` ni una `storage_reference`, solo bytes + `mime_type` +
`filename`.

## 5. Golden dataset

Un caso de benchmark por carpeta bajo `backend/benchmark/dataset/<id>/`:

```
benchmark/dataset/
  consulta_ficticia_01/
    audio.mp3          # NO versionado (ver .gitignore) — aportado localmente
    reference.json        # versionado — transcripción manual, fuente de verdad
    metadata.json           # versionado — términos críticos, casos de negación/lateralidad
```

`reference.json`/`metadata.json` son **opcionales por caso**: un caso sin
ellos se transcribe igualmente, solo que `benchmark/report.py` no calcula
las métricas que dependen de esos ficheros (§6-9) — nunca un error, ver
§12. `benchmark/dataset.py` resuelve la relación inequívoca entre audio,
referencia, metadata y resultados: `DatasetCase.id` es el mismo
identificador usado como nombre de carpeta, como `"id"` dentro de
`metadata.json`, y como nombre de fichero en `benchmark/results/<provider>/<id>.json`.

**Almacenamiento local.** Solo `reference.json`, `metadata.json`,
`*.example` y los `README.md` se versionan — `audio.*` está excluido por
`.gitignore` (`backend/benchmark/dataset/*/audio.*`). Cada persona que
ejecute el benchmark aporta sus propios ficheros de audio localmente, sin
que lleguen nunca al repositorio. Ver `backend/benchmark/dataset/README.md`
para el procedimiento paso a paso de añadir un caso nuevo.

La estructura anterior (`benchmark/audio/<fichero>.mp3`, plana, sin
asociar referencia/metadata) queda documentada como legacy en
`backend/benchmark/audio/README.md` — `benchmark.cli`/`benchmark.compare`
ya solo leen de `benchmark/dataset/`.

## 6. Reference format (`reference.json`)

Fuente de verdad para evaluación — la transcripción manual exacta de lo
que se dijo, segmento a segmento:

```json
{
  "language": "es",
  "speakers": [
    { "id": "audiologist", "label": "Audioprotesista" },
    { "id": "patient", "label": "Paciente" }
  ],
  "segments": [
    { "speaker": "audiologist", "start_ms": null, "end_ms": null, "text": "Buenos días, ¿en qué puedo ayudarle?" },
    { "speaker": "patient", "start_ms": null, "end_ms": null, "text": "Buenos días, desde hace unos meses noto que escucho peor." }
  ]
}
```

- `speaker` en cada segmento debe ser uno de los `id` declarados en
  `speakers` — se valida al cargar (`ReferenceValidationError`).
- `start_ms`/`end_ms` son **opcionales** (`null` si no se han medido a
  mano) — las métricas de esta fase (WER, terminología, negaciones,
  lateralidad, atribución de hablante) trabajan sobre texto y orden de
  palabras, nunca sobre tiempos, precisamente para no depender de
  timestamps de referencia que rara vez existen en una transcripción
  manual.
- `reference_full_text(reference)` (`benchmark/reference.py`) concatena
  el texto de todos los segmentos, en orden — es la "transcripción de
  referencia completa" contra la que se calcula WER (§7).

Implementado en `benchmark/reference.py` (`Reference`, `ReferenceSpeaker`,
`ReferenceSegment`, `load_reference`).

## 7. Metadata format (`metadata.json`)

```json
{
  "id": "consulta_ficticia_01",
  "description": "Consulta básica, ambiente limpio, dos hablantes",
  "language": "es",
  "duration_expected_seconds": 120,
  "number_of_speakers": 2,
  "environment": "quiet_clinic",
  "noise_level": "none",
  "critical_terms": ["hipoacusia", "acúfenos", "audiometría tonal", "vía aérea", "vía ósea"],
  "negation_cases": [
    {
      "concept": "vertigo",
      "expected": "negated",
      "patterns": {
        "negated": ["no tiene vértigo", "no vértigo", "niega vértigo"],
        "affirmed": ["tiene vértigo", "sí vértigo", "refiere vértigo"]
      }
    }
  ],
  "laterality_cases": [
    {
      "concept": "tinnitus",
      "laterality": "left",
      "patterns": {
        "left": ["oído izquierdo", "izquierdo"],
        "right": ["oído derecho", "derecho"],
        "bilateral": ["ambos oídos", "los dos oídos", "bilateral"]
      }
    }
  ],
  "notes": "Grabado con dos personas distintas para permitir evaluar diarización."
}
```

`environment` es uno de `quiet_clinic`/`office_noise`/
`background_conversation`/`street_noise` (validado al cargar).

**`negation_cases[].patterns`/`laterality_cases[].patterns` son una
extensión deliberada** sobre el ejemplo mínimo del encargo original: sin
un fragmento/patrón explícito no hay forma reproducible de comprobar la
hipótesis contra un `concept` abstracto como `"vertigo"` — ver §8-9 para
por qué y cómo se usan. **Nunca inventes casos que el audio no contenga**
— invalidaría la métrica; `critical_terms`/`negation_cases`/
`laterality_cases` deben reflejar exactamente lo que de verdad se dijo.

Implementado en `benchmark/dataset_metadata.py` (`DatasetMetadata`,
`NegationCase`, `LateralityCase`, `load_metadata`).

## 8. WER (Word Error Rate)

`benchmark/metrics/wer.py`, sobre `benchmark/metrics/alignment.py`
(alineación de Levenshtein a nivel de palabra):

```
WER = (substitutions + deletions + insertions) / reference_word_count
```

**Normalización aplicada antes de comparar** (`benchmark/metrics/text_normalize.py`,
`normalize_text`), documentada explícitamente:

1. minúsculas;
2. Unicode normalizado a NFC (nunca se retiran tildes: "acúfenos" y
   "acufenos" cuentan como palabras distintas — la tilde es
   semánticamente relevante en español y una transcripción que la pierda
   sí es un error real);
3. puntuación de frase retirada (`¿?¡!.,;:()"«»[]{}`) — nunca puntuación
   interna de una palabra (guiones, apóstrofos): "vía-aérea" no se
   fragmenta;
4. espacios múltiples colapsados a uno.

Deliberadamente **no** se aplica normalización más agresiva (stemming,
eliminación de stopwords, expansión de números a palabras...) — perdería
información semánticamente importante, en contra de lo pedido
explícitamente.

`compute_wer(reference_text, hypothesis_text) -> WerResult` expone
`value`, `substitutions`, `deletions`, `insertions`,
`reference_word_count` y la `alignment` completa (`list[AlignmentOp]`) —
terminología, negaciones y atribución de hablante reutilizan esta misma
alineación en vez de reimplementar su propia comparación de texto.

## 9. Terminology Error Rate

`benchmark/metrics/terminology.py`. Para cada término en
`metadata.critical_terms` (soporta términos multi-palabra, p. ej.
`"audiometría tonal"`):

| Estado | Significado |
|---|---|
| `not_in_reference` | El término no aparece en `reference.json` — no aplicable, no cuenta en `accuracy` |
| `recognized` | Aparece literalmente (normalizado) en la hipótesis |
| `omitted` | No aparece en la hipótesis, y ninguna de sus palabras (si es multi-palabra) tampoco |
| `substituted` | No aparece como frase completa, pero **alguna** de sus palabras sí (heurística de solapamiento parcial — nunca NLP: un término de una sola palabra solo puede ser `recognized`/`omitted`, no hay señal de solapamiento parcial posible) |

`accuracy = recognized / (recognized + omitted + substituted)` —
`None` si ningún término del listado aparece en la referencia.

## 10. Negation accuracy

`benchmark/metrics/negation.py`. Cada `negation_case` declara los
fragmentos esperados para su valor (`expected: "negated"|"affirmed"`) **y**
para el opuesto, en `patterns`. La hipótesis se busca contra ambos
conjuntos:

- Coincide un patrón del valor **esperado** → `pass`.
- Coincide un patrón del valor **opuesto** (y ninguno del esperado) →
  `fail` — el caso grave que pide detectar el encargo: `"no tiene
  vértigo"` transcrito como algo equivalente a `"tiene vértigo"`.
- Ninguno coincide → `not_detected` (el concepto no se mencionó en la
  hipótesis en absoluto — ni pasa ni falla, es información distinta de un
  `fail`).

Sin heurísticas clínicas: es comparación de subcadenas normalizadas
contra patrones **explícitos**, reproducible y testeable — nunca un
intento de "entender" la frase.

## 11. Laterality accuracy

`benchmark/metrics/laterality.py` — mismo principio que negaciones (§10),
con tres valores posibles por caso (`left`/`right`/`bilateral`) en vez de
dos. `pass` si coincide el patrón de la lateralidad esperada; `fail` si
coincide el de una lateralidad **distinta** de la esperada (p. ej.
esperado `left`, detectado `right`); `not_detected` si ninguna lateralidad
declarada coincide.

## 12. Diarization metrics

`benchmark/metrics/diarization.py`. Sin DER académico completo
(explícitamente fuera de alcance, ver §1) — métricas interpretables:

| Campo | Cálculo |
|---|---|
| `reference_speaker_count` | `len(reference.speakers)` — `null` sin `reference.json` |
| `detected_speaker_count` | Nº de labels de hablante distintos en los segmentos del proveedor |
| `speaker_count_match` | `reference_speaker_count == detected_speaker_count` |
| `number_of_reference_segments` | `len(reference.segments)` |
| `number_of_provider_segments` | `len(result.segments)` |
| `attribution_accuracy` | Ver abajo — `null` si no hay `reference.json`, no hay segmentos con hablante, o no hay palabras alineables |

**Atribución de hablante** (solo con `reference.json`): se alinean las
palabras de referencia (cada una etiquetada con su `speaker` del
segmento al que pertenece) contra las palabras de la hipótesis (etiquetadas
con el label del proveedor), reutilizando `align_words` (§8) — sin usar
timestamps. Sobre los pares alineados (`match`/`sub`), se calcula por
**voto mayoritario** qué `speaker` de referencia corresponde a cada label
del proveedor (el proveedor puede llamar `"speaker_1"` a quien la
referencia llama `"audiologist"` — no es un error mientras el mapeo sea
consistente). `attribution_accuracy` es la proporción de palabras
alineadas donde, tras aplicar ese mapeo, el hablante coincide.

Sin `reference.json`, `diarization` sigue reportando lo detectable del
propio resultado del proveedor (`detected_speaker_count`,
`number_of_provider_segments`), con el resto de campos en `null`.

## 13. Model traceability (AssemblyAI)

`AssemblyAITranscriptionProvider._normalize()` extrae, sin nunca
inventar un valor:

- `model_name`: primer campo presente entre `speech_model`,
  `language_model`, `acoustic_model` (distintas versiones/planes de la
  API han usado nombres distintos) — `None` si ninguno está presente.
- `provider_metadata` (se persiste en `AIGenerationRun.raw_response` —
  nunca el JSON completo de AssemblyAI, solo esto):
  ```python
  {
      "transcript_id": ...,
      "speaker_labels_requested": True,   # siempre True: el provider lo pide siempre
      "diarization_used": bool(segments),  # si el proveedor realmente devolvió >0 utterances
      "language_code_requested": "es",      # lo que pedimos
      "language_code_detected": ...,          # lo que devuelve el proveedor
      "punctuate": ...,
  }
  ```

**Por qué no el `raw_response` completo**: contendría el texto
transcrito duplicado (ya vive en `TranscriptionResult.text`), timestamps
por palabra (ruido para auditoría, no aporta trazabilidad de "qué se
configuró"), y en general más superficie de la necesaria — "extraer
únicamente metadata útil" (ver instrucción original de esta fase).

## 14. Real cost estimation

**`MockCostEstimator`/`estimated_cost_usd: "0"` nunca debe presentarse
como coste real** — de ahí `AudioCostEstimator`
(`app/integrations/domain/audio_cost_estimator.py`), un puerto **distinto**
de `CostEstimator` (pensado para tokens de LLM, no para duración de
audio — mezclar ambos modelos de coste habría producido estimaciones sin
sentido):

```python
class CostEstimateSource(StrEnum):
    MOCK = "mock"              # MockAudioCostEstimator — sin relación con el coste real
    PRICING_TABLE = "pricing_table"  # tabla de precios mantenida a mano — aproximación
    PROVIDER = "provider"        # el propio proveedor devolvió un coste (no es el caso de AssemblyAI hoy)

@dataclass(slots=True, frozen=True)
class CostEstimate:
    amount_usd: Decimal
    source: CostEstimateSource
    pricing_version: str | None
    pricing_effective_date: str | None
```

`PricingTableAudioCostEstimator` (`app/integrations/providers/pricing_table_audio_cost_estimator.py`)
usa `app/integrations/pricing.py` — **único punto de verdad** para
precios, nunca hardcodeados dispersos por el código:

```python
PRICING_VERSION = "2026-08-11.1"        # cámbialo si actualizas cualquier precio
PRICING_EFFECTIVE_DATE = "2026-08-11"     # fecha en que ESTE repo revisó los precios
DEFAULT_ASSEMBLYAI_PRICE_PER_HOUR_USD = Decimal("0.15")  # orientativo, ver aviso abajo
```

> **Nunca facturación autoritativa.** El precio por defecto es una
> aproximación orientativa (conocimiento general, no verificada contra la
> página de precios vigente de AssemblyAI en el momento de uso). Antes de
> tomar cualquier decisión basada en coste real, confirma el precio
> actual en su documentación oficial y ajusta
> `ASSEMBLYAI_PRICE_PER_HOUR_USD` en `.env` si hace falta — el estimador
> lo lee de `Settings`, nunca hay que tocar código para corregir el
> precio.

`build_audio_cost_estimator(settings, provider_name=None)` resuelve
`mock`→`MockAudioCostEstimator`, `assemblyai`→`PricingTableAudioCostEstimator`;
un proveedor no registrado (p. ej. uno añadido a `TRANSCRIPTION_PROVIDER_FACTORIES`
pero no aún a este registro) **degrada a `MockAudioCostEstimator`** en
vez de lanzar — el coste es información auxiliar, no debe poder romper
un benchmark que por lo demás funciona.

## 15. Cómo ejecutar un benchmark

Dentro del contenedor backend (`docker compose exec backend ...`, working
dir `/app`):

```bash
python -m benchmark.cli consulta_ficticia_01 --providers mock,assemblyai
```

- El primer argumento es el `audio_id` — el nombre de la carpeta bajo
  `benchmark/dataset/`, no una ruta de fichero.
- `--providers` acepta una lista separada por comas; por defecto `mock`.
- Requiere que `ASSEMBLYAI_API_KEY` esté configurada si se incluye
  `assemblyai` en la lista — si falta, ese proveedor concreto aparece
  como `error` en la tabla de salida (el resto de proveedores de la lista
  se ejecutan igualmente; un proveedor que falla nunca aborta el
  benchmark completo).
- Sin `reference.json`/`metadata.json` en el caso, la CLI avisa por
  consola de qué métricas no se calcularon — nunca falla.

## 16. Formato de resultados (esquema extendido, Fase 5.1)

```
benchmark/results/
  mock/
    consulta_ficticia_01.json
  assemblyai_baseline/
    consulta_ficticia_01.json
  assemblyai_optimized/
    consulta_ficticia_01.json
  deepgram_nova3_baseline/
    consulta_ficticia_01.json
  comparisons/
    consulta_ficticia_01.json     # generado por benchmark.compare, ver §17
```

Un fichero por `(proveedor, audio_id)`. Esquema completo
(`benchmark/report.py`, `build_report`):

```json
{
  "provider": "assemblyai",
  "model": "best",
  "audio_id": "consulta_ficticia_01",
  "audio_duration_ms": 115000,
  "processing_time_ms": 12279,
  "real_time_factor": 0.1068,
  "estimated_cost_usd": "0.0047916...",
  "estimated_cost_source": "pricing_table",
  "pricing_version": "2026-08-11.1",
  "pricing_effective_date": "2026-08-11",
  "language": "es",
  "succeeded": true,
  "error": null,
  "ran_at": "2026-08-11T10:00:00+00:00",
  "transcription": {
    "text": "...",
    "word_count": 308,
    "segments": [{ "speaker": "A", "start_ms": 0, "end_ms": 4300, "text": "..." }]
  },
  "metrics": {
    "wer": { "value": 0.12, "substitutions": 3, "deletions": 1, "insertions": 0, "reference_word_count": 33 },
    "terminology": { "accuracy": 0.85, "details": [{ "term": "hipoacusia", "present_in_reference": true, "status": "recognized" }] },
    "negations": { "passed": 2, "failed": 0, "details": [{ "concept": "vertigo", "expected": "negated", "result": "pass", "matched_pattern": "no vértigo" }] },
    "laterality": { "passed": 1, "failed": 0, "details": [{ "concept": "tinnitus", "expected": "left", "result": "pass", "matched_pattern": "izquierdo", "matched_laterality": "left" }] },
    "diarization": { "reference_speaker_count": 2, "detected_speaker_count": 1, "speaker_count_match": false, "attribution_accuracy": null, "number_of_reference_segments": 6, "number_of_provider_segments": 1 }
  },
  "capabilities": { "diarization": false, "timestamps": true, "confidence": true }
}
```

Cada bloque de `metrics{}` es `null` si no hay datos suficientes para
calcularlo (§5) — nunca un error. **Nota de adaptación**: `estimated_cost_usd`
se serializa como `string` (no `number`) para preservar la precisión
decimal del coste (`Decimal`, nunca `float`) — equivalencia funcional con
el ejemplo del encargo, que usaba `0` solo como placeholder ilustrativo.

Ni los audios (`benchmark/dataset/*/audio.*`) ni los resultados
(`benchmark/results/*`) se versionan — ver `.gitignore`.

### Cómo interpretar los resultados

- **`metrics.wer.value` bajo + `metrics.terminology.accuracy` alto**:
  candidato preferente para ese tipo de audio.
- **`metrics.diarization.speaker_count_match: false`**: el proveedor no
  separó correctamente a los hablantes — caso real observado con
  AssemblyAI en la primera prueba de esta fase (un único speaker
  detectado en un audio de dos personas), ver informe de esa sesión.
- **`metrics.negations.failed > 0`**: señal grave — una negación clínica
  se invirtió en la transcripción; revisar `details` para ver exactamente
  qué concepto y qué patrón coincidió.
- **`estimated_cost_source: "mock"`**: el coste mostrado es siempre `0`,
  no reflejar como si fuera real en ningún informe.

## 17. Comparison report

```bash
python -m benchmark.compare consulta_ficticia_01
```

Lee `benchmark/results/<provider>/<audio_id>.json` de cada proveedor que
tenga resultado para ese audio (nunca ejecuta ninguna transcripción —
solo agrega resultados ya generados por `benchmark.cli`), imprime una
tabla por terminal con `provider`, `model`, `wer`, `terminology accuracy`,
`negation failures`, `laterality failures`, `detected speakers`,
`processing time`, `RTF` y `estimated cost`, y escribe el JSON agregado
en `benchmark/results/comparisons/<audio_id>.json`. Preparado para N
proveedores aunque hoy solo existan `mock`/`assemblyai` — cualquier
proveedor nuevo añadido según §3 aparece automáticamente en la
comparación en cuanto tenga un resultado generado.

## 18. Dataset roadmap

Objetivo inicial: 10 audios ficticios, cada uno grabado con consentimiento
de los participantes, nunca pacientes reales.

| # | `audio_id` sugerido | Enfoque |
|---|---|---|
| 01 | `consulta_ficticia_01` | Consulta básica, ambiente limpio, dos hablantes — plantilla ya preparada, ver §19 |
| 02 | `consulta_ficticia_02` | Acúfenos y lateralidad |
| 03 | `consulta_ficticia_03` | Historial de otitis y cirugía |
| 04 | `consulta_ficticia_04` | Exposición laboral a ruido |
| 05 | `consulta_ficticia_05` | Paciente mayor con habla lenta |
| 06 | `consulta_ficticia_06` | Paciente joven con habla rápida |
| 07 | `consulta_ficticia_07` | Interrupciones/crosstalk |
| 08 | `consulta_ficticia_08` | Ruido ambiente moderado (`environment: office_noise`) |
| 09 | `consulta_ficticia_09` | Terminología audiológica intensa |
| 10 | `consulta_ficticia_10` | Negaciones y lateralidad difíciles |

Cada uno sigue la estructura de §5-7: `audio.<ext>` + `reference.json` +
`metadata.json` bajo `benchmark/dataset/<audio_id>/`.

## 19. Perfiles AssemblyAI: `baseline` vs `optimized` (Fase 5.2)

**Motivación**: la primera prueba real (dos personas distintas, ver nota
al principio de este documento) detectó un único speaker con la
configuración por defecto (`speaker_labels=True`, sin más parámetros).
Antes de considerar un segundo proveedor, esta fase comprueba si una
configuración distinta — pero **oficialmente soportada hoy** por
AssemblyAI, nunca supuesta — resuelve el problema sobre el mismo audio.

### Perfil `assemblyai_baseline`

Idéntico al proveedor `"assemblyai"` de producción — mismo payload HTTP
que la Fase 5, sin ningún parámetro nuevo:

```json
{ "audio_url": "...", "language_code": "es", "speaker_labels": true }
```

### Perfil `assemblyai_optimized`

Añade, todos verificados contra la documentación oficial vigente
(nunca supuestos):

| Parámetro | Valor | Variable de entorno | Por qué |
|---|---|---|---|
| `speech_models` | `["universal-3-5-pro"]` | `ASSEMBLYAI_OPTIMIZED_SPEECH_MODEL` | Modelo más reciente; único que soporta `keyterms_prompt` |
| `speakers_expected` | `2` | `ASSEMBLYAI_OPTIMIZED_SPEAKERS_EXPECTED` | Ver aviso de conocimiento a priori, abajo |
| `domain` | `"medical-v1"` (Medical Mode) | `ASSEMBLYAI_OPTIMIZED_MEDICAL_MODE` | Terminología clínica — soporta español |
| `keyterms_prompt` | `AUDIOLOGY_KEYTERMS_ES` (`app/integrations/keyterms.py`, `KEYTERM_SET_VERSION="audiology-es-v1"`) | `ASSEMBLYAI_OPTIMIZED_KEYTERMS_ENABLED` | Vocabulario audiológico — solo `universal-3-5-pro` |

**Aviso sobre `speakers_expected` — conocimiento a priori.** Fijarlo a
`2` asume que la conversación es exactamente un profesional y un
paciente. Es una asunción **válida para una consulta audioprotésica
típica**, pero **nunca debe convertirse en una suposición global del
producto**: pueden existir acompañantes, más de un profesional, o
consultas con más participantes. Por eso es configurable
(`ASSEMBLYAI_OPTIMIZED_SPEAKERS_EXPECTED`, admite `null`), no una
constante — la arquitectura soporta tanto `expected_speaker_count = null`
como `= 2` según el contexto de cada caso del dataset, decidido caso a
caso, no de una vez para todo el producto.

**Limitación conocida para `consulta_ficticia_01` específicamente**: la
documentación de AssemblyAI indica que `speakers_expected` **se ignora en
audios de menos de 2 minutos**. El audio real de esta prueba dura ~115s
(1 min 55s) — por debajo del umbral. Es posible que este parámetro no
tenga ningún efecto en el resultado de esta prueba concreta; el resto de
mejoras (`speech_models`, Medical Mode, `keyterms_prompt`) no tienen esa
limitación de duración.

**Medical Mode** no se asume que mejore diarización — su objetivo medido
es terminología audiológica y WER (ver criterios de comparación, §12 del
encargo de esta fase). Se registra explícitamente `medical_mode` en
`provider_metadata` y en el JSON de resultados.

**Model traceability**: `AssemblyAITranscriptionProvider` captura
`model_name` (best-effort) y, en `provider_metadata`,
`speech_models_requested`/`speakers_expected_requested`/`medical_mode`/
`keyterm_prompting`/`keyterm_set_version` — nunca el `raw_response`
completo (ver §13).

### Normalización: utterances → words → sin segmentos

Si `utterances` no está disponible pero `words[].speaker` sí lo está, el
proveedor agrupa palabras consecutivas del mismo hablante en segmentos
sintéticos en vez de colapsar todo en un único segmento — ver
`_segments_from_transcript` en `assemblyai_transcription_provider.py`.
El contrato normalizado que ve el resto del sistema (`{"text",
"language", "duration_ms", "segments"}`) no cambia — sigue sin saber si
AssemblyAI devolvió `utterances`, `words` u otra estructura.

### Coste por componentes

`PricingTableAudioCostEstimator` ya no aplica un precio plano: suma el
precio base del modelo más cada add-on activo (§14), verificados contra
https://www.assemblyai.com/pricing el 2026-08-11:

| Componente | USD/hora |
|---|---|
| Universal-2 (base) | $0.15 |
| Universal-3.5 Pro (base) | $0.21 |
| Diarización (`speaker_labels`) | +$0.02 |
| Medical Mode | +$0.15 |
| Keyterms Prompting | +$0.05 |

`assemblyai_baseline` con diarización (Universal-2 asumido, ver
`ASSEMBLYAI_DEFAULT_BASE_MODEL`): **$0.17/h**. `assemblyai_optimized`
completo (Universal-3.5 Pro + diarización + Medical Mode + keyterms):
**$0.43/h** — más de 2.5× el coste de baseline. El componente activo se
lee de `provider_metadata` (misma fuente que la trazabilidad de modelo,
sin una segunda fuente de verdad que pueda divergir) — nunca inventado.

### Ejecutar el experimento

```bash
docker compose exec backend python -m benchmark.cli consulta_ficticia_01 --providers assemblyai_baseline,assemblyai_optimized
docker compose exec backend python -m benchmark.compare consulta_ficticia_01
```

Resultados en `benchmark/results/assemblyai_baseline/consulta_ficticia_01.json`
y `benchmark/results/assemblyai_optimized/consulta_ficticia_01.json` —
nunca se pisan entre sí ni con el resultado antiguo bajo
`benchmark/results/assemblyai/` (proveedor de producción, sin perfil).

### Criterio de éxito de diarización

Se considera diarización **satisfactoria** para este dataset únicamente
si, simultáneamente: detecta 2 speakers; `speaker_count_match = true`;
`attribution_accuracy` razonablemente alta; y ningún intercambio de
speaker cambia la interpretación clínica del texto. Detectar
simplemente "A" y "B" sin que la atribución sea correcta **no es
suficiente**.

### Añadir un caso nuevo al dataset (grabación)

Para el resto del roadmap (§18, casos 02-10, que sí requieren grabar
desde cero): ver `backend/benchmark/dataset/README.md` §Cómo añadir un
caso nuevo — misma estructura de 5 pasos (audio + `reference.json` +
`metadata.json`), sin repetirla aquí.

## 20. Integración de Deepgram Nova-3 (Fase 5.3)

**Motivación**: la Fase 5.2 concluyó que AssemblyAI (baseline u
optimized) no resuelve la diarización de forma satisfactoria (§19,
criterio de éxito) — `assemblyai_optimized` sigue fusionando ~83% del
diálogo en un único speaker, a más del doble de coste de `baseline`, sin
mejorar el resultado de fondo. Deepgram Nova-3 se evalúa como candidato
alternativo, específicamente por su diarización.

### Investigación previa (documentación oficial, nunca supuesta)

Verificado contra `developers.deepgram.com` en el momento de esta fase:

- Endpoint: `POST /v1/listen` — **síncrono**, sin polling: la respuesta ya
  contiene la transcripción completa (a diferencia del flujo
  subida+poll de AssemblyAI).
- El audio se envía como **cuerpo binario** de la petición
  (`Content-Type` = MIME del audio), sin paso previo de subida.
- Autenticación: cabecera `Authorization: Token <api_key>`.
- Parámetros relevantes (query string): `model=nova-3`, `language=es`,
  `diarize=true`, `utterances=true`, `smart_format=true`,
  `punctuate=true`, `keyterm=<término>` (repetible, ≤500 tokens en
  total, exclusivo de Nova-3).
- `results.utterances[]` trae `speaker` como **entero** y `start`/`end`
  en **segundos** — a diferencia de AssemblyAI (`start`/`end` en
  milisegundos), conversión explícita `*1000` en
  `_segments_from_transcript` (ver nota en el docstring del módulo).
- `metadata.models[]` + `metadata.model_info{uuid: {name, version,
  arch}}` — trazabilidad de modelo (§13, mismo principio que AssemblyAI).
- Endpoint regional EU disponible y en general disponibilidad:
  `https://api.eu.deepgram.com` (mismas credenciales, sin activación ni
  coste adicional) — residencia de datos dentro de la UE.

### Endpoint EU por defecto — decisión deliberada

`DEEPGRAM_BASE_URL` por defecto es `https://api.eu.deepgram.com`, no el
genérico `api.deepgram.com`. Decisión explícita para un producto
sanitario: preferir residencia de datos en la UE siempre que esté
disponible oficialmente, sin coste ni fricción adicional. Configurable
vía `Settings.deepgram_base_url` — nunca hardcodeado sin poder
override-arse. `provider_metadata.region` (`"eu"`/`"us"`) registra cuál
se usó realmente en cada resultado.

### `DeepgramTranscriptionProvider`

`app/integrations/providers/deepgram_transcription_provider.py`,
implementa `TranscriptionProvider` sin modificar el contrato normalizado
(§4). Normalización de segmentos con la misma prioridad que AssemblyAI
(§19): 1) `results.utterances` con speaker → 2) `words[].speaker`
agrupadas en segmentos sintéticos consecutivos del mismo hablante → 3)
sin segmentos si ninguna de las dos trae hablante.

`provider_metadata` (nunca el `raw_response` completo — mismo criterio
que §13):

```python
{
    "request_id": ...,
    "model_version": ...,
    "model_arch": ...,
    "diarization_requested": True,
    "diarization_used": bool(segments),
    "smart_format_requested": True,
    "language_code_requested": "es",
    "keyterm_prompting": ...,
    "keyterm_set_version": ...,
    "api_base": "https://api.eu.deepgram.com",
    "region": "eu",
}
```

### Configuración

```bash
TRANSCRIPTION_PROVIDER=deepgram      # activa Deepgram en producción (pipeline real)
DEEPGRAM_API_KEY=...                   # obligatoria si se activa
DEEPGRAM_BASE_URL=https://api.eu.deepgram.com   # EU por defecto, ver arriba
DEEPGRAM_LANGUAGE_CODE=es
DEEPGRAM_MODEL=nova-3
```

`.env.example` documenta estas variables con placeholders
(`CHANGE_ME_LOCAL_ONLY`), nunca valores reales (regla no negociable #5 de
`CLAUDE.md`).

### Perfiles de benchmark

Mismo patrón que AssemblyAI (§19) — cada perfil es una entrada del
registro de `app/integrations/factory.py`, `"deepgram"` (producción) es
un alias byte-idéntico de `"deepgram_nova3_baseline"`:

| Perfil | Estado en esta fase | Config |
|---|---|---|
| `deepgram_nova3_baseline` | Único perfil llamado esta fase | español, diarización, timestamps, utterances, smart_format, Nova-3 — sin keyterms |
| `deepgram_nova3_keyterms` | Preparado, **no llamado** esta fase | baseline + `keyterm` con `AUDIOLOGY_KEYTERMS_ES` (`app/integrations/keyterms.py`) |

Nombrado `deepgram_nova3_*` (no solo `deepgram_*`) porque Deepgram puede
publicar modelos futuros (Nova-4...) que serán perfiles nuevos, nunca una
sobrescritura del actual.

### Coste

`app/integrations/pricing.py`, tabla **independiente** de la de
AssemblyAI (nunca mezcladas — funciones y campos separados), verificada
contra `deepgram.com/pricing`:

| Componente | USD/min |
|---|---|
| Nova-3 monolingüe (pre-grabado, base) | $0.0077 |
| Diarización | +$0.0020 |
| Keyterm prompting | +$0.0012 |
| Smart Format | incluido, sin coste adicional |

`medical_mode` no existe como concepto en Deepgram — el estimador lo
ignora silenciosamente si se pasa (nunca un error), ver
`test_deepgram_medical_mode_se_ignora_silenciosamente_no_existe_en_deepgram`.
Mismo modelo de trazabilidad que AssemblyAI: `pricing_version`,
`pricing_effective_date`, `estimated_cost_source = "pricing_table"`.

### Ejecutar el benchmark

```bash
docker compose exec backend python -m benchmark.cli consulta_ficticia_01 --providers deepgram_nova3_baseline
docker compose exec backend python -m benchmark.compare consulta_ficticia_01
```

Resultado en
`benchmark/results/deepgram_nova3_baseline/consulta_ficticia_01.json` —
nunca pisa los resultados de AssemblyAI. `benchmark.compare` agrega
automáticamente cualquier perfil con resultado disponible, incluidos los
tres (`assemblyai_baseline`, `assemblyai_optimized`,
`deepgram_nova3_baseline`) en cuanto los tres existan.

### Estado al cierre de esta fase

Implementación, configuración, factory, pricing y tests (17 tests en
`test_deepgram_provider.py`, más los de pricing/factory) están completos
y en verde. La llamada real a Deepgram (`deepgram_nova3_baseline`) y la
comparación de 3 vías con AssemblyAI (`baseline`/`optimized`) ya se han
ejecutado sobre `consulta_ficticia_01` con el golden dataset definitivo
(§5) — WER 0.03 (AssemblyAI, ambos perfiles) vs. 0.05 (Deepgram),
terminología 1.00 (AssemblyAI) vs. 0.91 (Deepgram), negaciones/
lateralidad 100% en los tres perfiles, atribución de hablante 0.59
(`assemblyai_baseline`, 1 solo segmento detectado) / 0.74
(`assemblyai_optimized`) / 0.92 (`deepgram_nova3_baseline`). Detalle
completo en `benchmark/results/comparisons/consulta_ficticia_01.json`.
Pendiente: la clasificación de errores CRÍTICO/MAYOR/MENOR (análisis
cualitativo, no implementado en código — fuera de alcance de la
regeneración del benchmark).

## 21. Tests: nunca llamadas reales

Todos los tests de `AssemblyAITranscriptionProvider`/
`DeepgramTranscriptionProvider` inyectan un `httpx.AsyncClient`
construido con `transport=httpx.MockTransport(handler)` — nunca
contactan `api.assemblyai.com` ni `api.eu.deepgram.com`. Los tests de
`BenchmarkRunner` inyectan proveedores falsos (nunca un proveedor real)
del mismo modo. Ver `backend/tests/test_assemblyai_provider.py`,
`backend/tests/test_deepgram_provider.py` (17 tests: normalización desde
`utterances`/`words`, conversión de segundos a milisegundos, prioridad
`utterances` > `words`, sin segmentos si no hay hablante, trazabilidad de
modelo, forma completa de `provider_metadata`, región EU/US, cuerpo
binario + parámetros de la petición, `keyterm` repetido, errores HTTP,
timeout, clave ausente, audio ausente, secreto nunca en excepción ni en
`json.dumps(provider_metadata)`),
`backend/tests/test_benchmark_runner.py`,
`backend/tests/test_benchmark_wer.py`,
`backend/tests/test_benchmark_terminology.py`,
`backend/tests/test_benchmark_negation.py`,
`backend/tests/test_benchmark_laterality.py`,
`backend/tests/test_benchmark_diarization.py`,
`backend/tests/test_benchmark_dataset.py`,
`backend/tests/test_benchmark_report.py`,
`backend/tests/test_benchmark_compare.py`,
`backend/tests/test_audio_cost_estimator.py` (pricing AssemblyAI y
Deepgram, tabla nunca compartida) y `backend/tests/test_transcription_factory.py`
(perfiles `assemblyai_baseline`/`assemblyai_optimized`, Fase 5.2, y
`deepgram`/`deepgram_nova3_baseline`/`deepgram_nova3_keyterms`, Fase 5.3).

## 22. Backlog (preparado, no implementado)

- **OpenAI / Speechmatics / Azure Speech / Google Speech / AWS
  Transcribe / Whisper local**: cada uno es una entrada nueva en los dos
  registros de `app/integrations/factory.py` (§3) — sin cambios en
  `benchmark/` ni en `ai_pipeline/`. Deepgram Nova-3 ya está implementado
  (§20).
- **Clasificación de errores CRÍTICO/MAYOR/MENOR**: no implementada en
  código — análisis cualitativo pendiente sobre los resultados ya
  regenerados (§20).
- **Perfil `deepgram_nova3_keyterms`**: implementado y testeado, pero no
  llamado esta fase — solo tras establecer el baseline real, igual que
  con AssemblyAI (§19).
- ~~Golden dataset de `consulta_ficticia_01` (`reference.json`/
  `metadata.json` reales)~~ — **resuelto**: golden dataset definitivo
  aportado y validado, WER/terminología/negaciones/lateralidad/
  diarización recalculados para los tres perfiles (§20).
- **HTML/dashboard**: explícitamente fuera de alcance (ver §1).
- **`estimated_cost_source = "provider"`**: el código ya distingue esta
  fuente en `CostEstimateSource`, pero ningún proveedor implementado hoy
  devuelve coste en su propia respuesta — en cuanto uno lo haga, es
  cuestión de leerlo en `_normalize()` y priorizarlo sobre la tabla de
  precios.
- **Duración real del audio en la subida** (`audio/domain/validation.py`):
  sigue confiando en `duration_seconds` proporcionado por el cliente, no
  lo extrae del binario — confirmado como impreciso con datos reales en
  la primera prueba de esta fase (242 s estimados vs. 115 s reales según
  AssemblyAI).
- **`GET /audio-recordings/{id}/download`**: fuera de alcance, ver Fase 5
  en [development-plan.md](development-plan.md).
- **Soporte de `keyterms_prompt` para español**: la documentación oficial
  consultada no confirma ni descarta explícitamente que funcione en
  idiomas no ingleses — se activa igualmente en `assemblyai_optimized`
  (comportamiento documentado: si no aplica, AssemblyAI lo ignora sin
  error) y se evalúa con datos reales en el resultado del experimento.
- **Integración de Deepgram Nova-3**: decisión pendiente del resultado
  del experimento baseline/optimized (§19) — ver informe de esta sesión
  para el criterio de decisión exacto. No implementado todavía en ningún
  caso.
- **`RetentionCleanupService`**: sigue siendo Fase 7, sin cambios.
