# Benchmark de proveedores de transcripción — Fase 5

Plataforma permanente para comparar proveedores de transcripción
(AssemblyAI, Deepgram, OpenAI, Speechmatics, Azure Speech, Google Speech,
AWS Transcribe, Whisper local...) usando exactamente los mismos audios.
Ver [development-plan.md](development-plan.md) Fase 5 para el criterio de
aceptación completo y [architecture.md](architecture.md) para el resto de
la arquitectura del backend.

## 1. Qué NO es esta fase

- No integra ningún LLM (Summary/ClinicalFlags/MissingInformation/Anamnesis
  siguen siendo Mock, sin cambios).
- No calcula WER (Word Error Rate) todavía — preparado, no implementado
  (ver §6 y §9).
- No genera HTML ni dashboards — solo JSON por ejecución.
- No implementa Deepgram/OpenAI/Speechmatics/Azure/Google/AWS/Whisper —
  solo `mock` y `assemblyai`. Añadirlos es extender el registro descrito
  en §3, no rediseñar nada.

## 2. Arquitectura

Dos piezas, deliberadamente independientes:

```
app/integrations/                          benchmark/
  domain/                                     runner.py    → BenchmarkRunner
    transcription_provider.py                 report.py    → build_report / write_report
      TranscriptionProvider (Protocol)         cli.py       → python -m benchmark.cli
      TranscriptionInput / AudioForTranscription  audio/    → dataset local (no versionado)
      TranscriptionResult / TranscriptionSegment  results/  → JSON por proveedor (no versionado)
  mocks/
    mock_transcription_provider.py
  providers/
    assemblyai_transcription_provider.py
  factory.py  → build_transcription_provider(settings, name=None)
```

`benchmark/` **no depende de `app/ai_pipeline/`**: no toca la base de
datos, no crea `AIArtifact`, no requiere una sesión clínica real ni un
`clinical_session_id` verdadero (usa uno aleatorio, opaco, exigido por el
contrato pero nunca persistido). Solo depende de `app/integrations/` — el
mismo contrato `TranscriptionProvider` que usa el AI Pipeline real (ver
§5), para que "comparar proveedores" y "usar un proveedor en producción"
sean exactamente la misma abstracción, nunca dos implementaciones
paralelas que puedan divergir.

`app/integrations/factory.py` expone un único registro,
`TRANSCRIPTION_PROVIDER_FACTORIES: dict[str, Callable[[Settings], TranscriptionProvider]]`,
consumido por:

- La app (`build_transcription_provider(settings)`, sin segundo
  argumento): un único proveedor activo, el de `TRANSCRIPTION_PROVIDER`.
- `benchmark/` (`build_transcription_provider(settings, name)`, con
  segundo argumento): construye varios proveedores distintos en la misma
  ejecución, uno por cada `--providers` pedido.

## 3. Cómo añadir un proveedor nuevo

Un único cambio, en `app/integrations/factory.py`:

```python
TRANSCRIPTION_PROVIDER_FACTORIES: dict[str, Callable[[Settings], TranscriptionProvider]] = {
    "mock": lambda settings: MockTranscriptionProvider(),
    "assemblyai": lambda settings: AssemblyAITranscriptionProvider(...),
    "deepgram": lambda settings: DeepgramTranscriptionProvider(
        api_key=settings.deepgram_api_key,
        ...
    ),
}
```

Pasos completos:

1. Implementar `app/integrations/providers/deepgram_transcription_provider.py`
   con una clase que satisfaga `TranscriptionProvider` (`async def
   transcribe(self, input: TranscriptionInput) -> TranscriptionResult`),
   devolviendo siempre el contrato normalizado (§4) — nunca un `dict`
   crudo de la API del proveedor.
2. Añadir la configuración necesaria a `Settings`
   (`app/core/config.py`) — solo variables de entorno, nunca
   credenciales hardcodeadas (regla no negociable #5 de `CLAUDE.md`).
   Documentar la variable en `.env.example` con un placeholder, nunca un
   valor real.
3. Añadir la entrada al registro de arriba.
4. Añadir `"deepgram"` a la lista de valores válidos de
   `TRANSCRIPTION_PROVIDER` en `Settings` (`Literal[...]`) si se quiere
   activar como proveedor de producción del pipeline, no solo de
   benchmark.
5. Tests con HTTP mockeado (nunca llamadas reales, ver §8) — mismo patrón
   que `tests/test_assemblyai_provider.py`.

**Ningún otro módulo cambia**: ni `ai_pipeline/`, ni `audio/`, ni
`benchmark/runner.py`/`cli.py`, ni la API. Ese es el criterio de
aceptación arquitectónico de esta fase.

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

## 5. Proveedor real: AssemblyAI

`AssemblyAITranscriptionProvider`
(`app/integrations/providers/assemblyai_transcription_provider.py`) usa
la API REST oficial v2 vía `httpx` (cliente HTTP genérico, no un SDK de
terceros):

1. `POST /v2/upload` — sube los bytes, devuelve `upload_url`.
2. `POST /v2/transcript` — encola el job (`audio_url`, `language_code`,
   `speaker_labels: true`), devuelve `id`.
3. `GET /v2/transcript/{id}` — sondeo (`ASSEMBLYAI_POLL_INTERVAL_SECONDS`,
   por defecto 2s) hasta `status` en `{completed, error}` o hasta superar
   `ASSEMBLYAI_POLL_TIMEOUT_SECONDS` (por defecto 120s).

La API key viaja únicamente en la cabecera `authorization` de cada
petición — nunca se registra en logs ni aparece en el mensaje de ninguna
excepción. Si `TRANSCRIPTION_PROVIDER=assemblyai` sin
`ASSEMBLYAI_API_KEY`, la aplicación falla al arrancar (mismo patrón que
`FakeCurrentUserProvider`, ver `app/main.py` `lifespan`) — nunca en la
primera petición de un usuario real.

**Selección exclusivamente por configuración** (`TRANSCRIPTION_PROVIDER`
en `.env`), resuelta por Dependency Injection en `app/core/deps.py`
(`get_configured_transcription_provider`, cacheado). Ningún `if
provider == "assemblyai"` disperso por el código — la ramificación vive
en un único sitio, `app/integrations/factory.py`.

## 6. Métricas registradas

Por cada `(proveedor, audio)`, `benchmark/report.py` registra:

| Campo | Origen |
|---|---|
| `provider` | Nombre del proveedor (`mock`, `assemblyai`, ...) |
| `model` | Modelo usado, si el proveedor expone más de uno (`None` en esta fase) |
| `audio_file` | Nombre del fichero de audio |
| `ran_at` | Timestamp ISO de la ejecución |
| `succeeded` / `error` | Si la transcripción tuvo éxito; motivo si no |
| `response_time_ms` | Tiempo total (subida + cola + transcripción) |
| `audio_duration_ms` | `TranscriptionResult.duration_ms` |
| `detected_language` | `TranscriptionResult.language` |
| `estimated_cost_usd` | Vía `CostEstimator` (aproximación por nº de palabras, no facturación real) |
| `word_count` | Palabras del texto transcrito |
| `has_timestamps` | `True` si `segments` no es `None`/vacío |
| `diarization_available` | `True` si algún segmento tiene `speaker` no nulo |
| `segment_count` | `len(segments)` |
| `confidence` | `TranscriptionResult.confidence`, si el proveedor lo aporta |
| `text` | Transcripción completa |
| `wer` | Siempre `None` en esta fase — ver §9 (preparado, no calculado) |

## 7. Cómo ejecutar un benchmark

Dentro del contenedor backend (`docker compose exec backend ...`, working
dir `/app`):

```bash
python -m benchmark.cli benchmark/audio/consulta_ficticia_01.mp3 --providers mock,assemblyai
```

- `--providers` acepta una lista separada por comas; por defecto `mock`.
- Requiere que `ASSEMBLYAI_API_KEY` esté configurada si se incluye
  `assemblyai` en la lista — si falta, ese proveedor concreto aparece
  como `error` en la tabla de salida (el resto de proveedores de la lista
  se ejecutan igualmente; un proveedor que falla nunca aborta el
  benchmark completo).
- La CLI imprime una tabla resumen por consola y escribe un JSON por
  proveedor (ver §8).

## 8. Formato de resultados

```
benchmark/results/
  mock/
    consulta_ficticia_01.json
  assemblyai/
    consulta_ficticia_01.json
```

Un fichero por `(proveedor, audio)`, nombrado `<nombre-audio-sin-extension>.json`,
con el contenido descrito en §6. Ni los audios (`benchmark/audio/*`) ni
los resultados (`benchmark/results/*`) se versionan — ver
`benchmark/audio/README.md` y `.gitignore` — cada persona que ejecute el
benchmark aporta sus propios audios ficticios y genera sus propios
resultados localmente.

### Cómo interpretar los resultados

- **`response_time_ms` bajo + `confidence` alto**: candidato preferente
  para ese tipo de audio.
- **`diarization_available: false`** con un audio de varios hablantes:
  el proveedor no soporta diarización o no se solicitó — no asumir que
  el audio tiene un único hablante.
- **`wer: null`**: todavía no hay una métrica objetiva de calidad de
  transcripción — comparar `text` manualmente contra lo realmente dicho
  en el audio ficticio hasta que se implemente §9.
- Comparar el mismo `audio_file` entre las carpetas de cada proveedor
  (`results/<provider>/<audio>.json`) — el nombre de fichero es idéntico
  entre proveedores precisamente para facilitar esa comparación.

## 9. Backlog (preparado, no implementado en esta fase)

- **WER (Word Error Rate)**: requiere una transcripción de referencia por
  audio (`benchmark/audio/<nombre>.reference.txt` o similar) contra la
  que comparar `text`. El campo `wer` ya existe en el JSON de resultados
  (`None` hoy) para no requerir una migración de formato el día que se
  implemente.
- **Deepgram / OpenAI / Speechmatics / Azure Speech / Google Speech / AWS
  Transcribe / Whisper local**: cada uno es una entrada nueva en
  `TRANSCRIPTION_PROVIDER_FACTORIES` (§3) — sin cambios en `benchmark/`
  ni en `ai_pipeline/`.
- **Informe comparativo persistido** (además de un JSON por proveedor):
  un `benchmark/results/<audio>.comparison.json` que agregue las métricas
  de todos los proveedores ejecutados para ese audio — hoy la comparación
  es manual, leyendo los JSON individuales.
- **HTML/dashboard**: explícitamente fuera de alcance de esta fase (ver
  §1).
- **Duración real del audio en la subida** (`audio/domain/validation.py`):
  esta fase confía en `duration_seconds` proporcionado por el cliente al
  subir el audio, no lo extrae del binario (evita añadir una dependencia
  de parseo de audio sin que se haya pedido explícitamente) — ver
  [development-plan.md](development-plan.md) Fase 5.
- **`GET /audio-recordings/{id}/download`**: documentado en una versión
  anterior de [api-specification.md](api-specification.md) §Audio, fuera
  de alcance de esta fase — ver Fase 5 en
  [development-plan.md](development-plan.md).

## 10. Tests: nunca llamadas reales

Todos los tests de `AssemblyAITranscriptionProvider` inyectan un
`httpx.AsyncClient` construido con `transport=httpx.MockTransport(handler)`
— nunca contactan `api.assemblyai.com`. Los tests de `BenchmarkRunner`
inyectan proveedores falsos (no `assemblyai` real) del mismo modo. Ver
`backend/tests/test_assemblyai_provider.py` y
`backend/tests/test_benchmark_runner.py`.
