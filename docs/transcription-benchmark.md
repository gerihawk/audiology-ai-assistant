# Benchmark de proveedores de transcripción — Fase 5 / Fase 5.1

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
proveedores. Este documento cubre ambas fases.

## 1. Qué NO es esta fase

- No integra ningún LLM (Summary/ClinicalFlags/MissingInformation/Anamnesis
  siguen siendo Mock, sin cambios).
- No implementa Deepgram/OpenAI/Speechmatics/Azure/Google/AWS/Whisper —
  solo `mock` y `assemblyai`. Añadirlos es extender el registro descrito
  en §3, no rediseñar nada.
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

Dos cambios, ambos en `app/integrations/`:

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
  assemblyai/
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

## 19. Cómo grabar y evaluar `consulta_ficticia_01` (dos personas)

1. Graba una conversación ficticia de 1-3 min entre dos personas
   distintas — una interpretando al audioprotesista, otra al paciente
   (voces distintas es importante: la primera prueba real de esta fase
   usó una única voz para ambos papeles y la diarización falló por
   completo — no es concluyente sobre AssemblyAI hasta repetirlo con dos
   voces reales).
2. Guarda el fichero como
   `backend/benchmark/dataset/consulta_ficticia_01/audio.mp3` (o
   `.wav`/`.m4a`/`.ogg`/`.webm`).
3. Copia `reference.json.example` → `reference.json` en esa misma carpeta
   y transcribe el audio a mano, segmento por segmento, con el `speaker`
   correcto (`audiologist`/`patient`).
4. Copia `metadata.json.example` → `metadata.json` y ajusta
   `critical_terms`/`negation_cases`/`laterality_cases` a lo que
   **realmente** contiene tu grabación.
5. Ejecuta manualmente (nunca de forma automática — ver §14 del encargo
   de esta fase):
   ```bash
   docker compose exec backend python -m benchmark.cli consulta_ficticia_01 --providers mock,assemblyai
   docker compose exec backend python -m benchmark.compare consulta_ficticia_01
   ```
6. Revisa `benchmark/results/assemblyai/consulta_ficticia_01.json` — en
   particular `metrics.diarization` (¿ahora sí separa dos hablantes?),
   `metrics.wer`, `metrics.terminology`, `metrics.negations`,
   `metrics.laterality`.

## 20. Tests: nunca llamadas reales

Todos los tests de `AssemblyAITranscriptionProvider` inyectan un
`httpx.AsyncClient` construido con `transport=httpx.MockTransport(handler)`
— nunca contactan `api.assemblyai.com`. Los tests de `BenchmarkRunner`
inyectan proveedores falsos (no `assemblyai` real) del mismo modo. Ver
`backend/tests/test_assemblyai_provider.py`,
`backend/tests/test_benchmark_runner.py`,
`backend/tests/test_benchmark_wer.py`,
`backend/tests/test_benchmark_terminology.py`,
`backend/tests/test_benchmark_negation.py`,
`backend/tests/test_benchmark_laterality.py`,
`backend/tests/test_benchmark_diarization.py`,
`backend/tests/test_benchmark_dataset.py`,
`backend/tests/test_benchmark_report.py`,
`backend/tests/test_benchmark_compare.py` y
`backend/tests/test_audio_cost_estimator.py`.

## 21. Backlog (preparado, no implementado)

- **Deepgram / OpenAI / Speechmatics / Azure Speech / Google Speech / AWS
  Transcribe / Whisper local**: cada uno es una entrada nueva en los dos
  registros de `app/integrations/factory.py` (§3) — sin cambios en
  `benchmark/` ni en `ai_pipeline/`.
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
- **`RetentionCleanupService`**: sigue siendo Fase 7, sin cambios.
