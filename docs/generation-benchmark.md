# Benchmark de generación LLM — Fase 6.2

Plataforma reproducible para comparar modelos de lenguaje en la
generación de artefactos clínicos, vía OpenRouter. Ver
[fase-6-rfc.md](fase-6-rfc.md) §6.2 para el diseño normativo y
[development-plan.md](development-plan.md) hito 6.2 para el criterio de
aceptación.

## 1. Objetivo

Medir, de forma reproducible y determinista, qué modelo/proveedor genera
mejor `SUMMARY`, `MISSING_INFORMATION` y `PATIENT_SUMMARY` — los tres
artefactos que el hito 6.3 activará en producción con el ganador de este
benchmark. Sin ese benchmark, elegir proveedor sería una decisión sin
evidencia.

**Alcance de 6.2 (RFC §10)**: `SUMMARY`, `MISSING_INFORMATION`,
`PATIENT_SUMMARY` — los mismos tres artefactos que el hito 6.3 activa con
el modelo ganador. `ANAMNESIS`/`SESSION_NOTES` requieren grounding real y
`applies_to()` (hito 6.4); `AnamnesisUpdateStep` es hito 6.5. Ninguno de
los tres entra en este benchmark.

## 2. Separación benchmark / producción

```
PRODUCCIÓN                          BENCHMARK
AIPipelineService                   benchmark/generation/
  -> PipelineSteps                    -> GenerationBenchmarkRunner
  -> Mock* (todavía)                    -> BenchmarkLLMClient (OpenRouter)
```

- `benchmark/generation/` **nunca** crea `AIArtifact`,
  `AIArtifactVersion` ni `AIGenerationRun` — un resultado de benchmark es
  un concepto propio, no un artefacto clínico (ver
  `test_generation_benchmark_isolation.py`).
- OpenRouter (`openrouter_client.py`) es **exclusivo de benchmark**. No
  existe ningún `LanguageModelProvider` productivo que lo use — la
  producción sigue enteramente con `Mock*` hasta el hito 6.3 (proveedor
  directo, sin OpenRouter de por medio, ver RFC §6.1).
- La app arranca sin `OPENROUTER_API_KEY`: es `None` por defecto en
  `Settings`, y `BenchmarkLLMClient` falla explícitamente
  (`OpenRouterAuthenticationError`) si se intenta usar sin ella — nunca
  una llamada anónima ni un fallback silencioso.
- `PATIENT_SUMMARY` sí existe ya como `AIArtifactType` (precondición de
  este hito, ver §5) pero **no tiene `PipelineStep`** ni entrada en
  `PIPELINE_STEP_ORDER` — el comportamiento de producción no cambia.

## 3. Dataset (`backend/benchmark/generation_dataset/`)

Un caso por carpeta, `<transcript_id>__<artifact_type>/`:

```
generation_dataset/
  consulta_ficticia_01__summary/
    input.json       # transcripción + artifact_type + contexto — versionado
    reference.json      # referencia HUMANA — versionado, nunca generada por IA
    metadata.json          # invariantes clínicas declaradas — versionado
  consulta_ficticia_01__missing_information/
    ...
  consulta_ficticia_01__patient_summary/
    ...
```

Todos los ficheros se versionan (sin binario que excluir, a diferencia
de `benchmark/dataset/*/audio.*`). Ver
`backend/benchmark/generation_dataset/README.md` para cómo añadir un caso.

### `input.json`

`id`, `language`, `artifact_type`, `session_type` (opcional),
`transcript`, `transcript_segments` (opcional), `context` (variables
adicionales permitidas para el prompt — p. ej. `summary_text` que
`missing_information`/`patient_summary` reciben como dependencia, ver RFC
§4.3/§4.5), `prompt_template` (opcional, fija el *nombre* de una
plantilla concreta), `case_metadata` (libre).

`context` siempre `dict[str, str]` — `RenderContext.variables` de
`PromptRenderer` no acepta otra cosa.

### `reference.json`

La referencia HUMANA de lo que debería generar el modelo — nunca la
salida de un LLM. `content` debe cumplir el mismo schema cerrado que
`app.ai_pipeline.domain.schemas.validate_content_schema` — es la MISMA
fuente de verdad que benchmark, schema validation, un futuro
`PipelineStep` y producción en el hito 6.3.

Un caso con `"content": null` está **pendiente**:
`GenerationBenchmarkRunner` se niega a invocar un modelo real para él
(`GenerationReferenceRequiredError`) — nunca se inventa la referencia
para poder avanzar.

### `metadata.json`

Solo las invariantes relevantes para el `artifact_type` del caso (nunca
todos los campos indiscriminadamente):

| Campo | Aplica a | Reutiliza |
|---|---|---|
| `required_facts` | todos | nuevo (`FactCase`) |
| `forbidden_facts` | todos | nuevo (`FactCase`) |
| `critical_terms` | todos | `benchmark.metrics.terminology` (ASR, sin cambios) |
| `negation_cases` | todos | `benchmark.dataset_metadata.NegationCase` (ASR, sin cambios) |
| `laterality_cases` | todos | `benchmark.dataset_metadata.LateralityCase` (ASR, sin cambios) |
| `numeric_cases` | todos | nuevo (`NumericCase`, mismo principio que negación/lateralidad) |
| `expected_missing_topics` | solo `missing_information` | nuevo (`FactCase`) |
| `max_length` | opcional | — |

## 4. Métricas deterministas

Ninguna usa LLM-as-judge como métrica principal — todas son comparación
de patrones/subcadenas normalizadas explícitas, reproducibles y
testeables (encargo §5-6).

- **Schema validity / evasive / grounding / safety**: reutilizadas tal
  cual de `app.ai_pipeline.domain.validation_pipeline.validate_generated_content`
  — el mismo pipeline que producción, invocado por el runner. Grounding
  es hoy un no-op estructural para los 3 tipos de 6.2 (ninguno declara
  `source_excerpt` en su schema); se activará solo cuando entre un
  `artifact_type` que sí lo declare (p. ej. `SESSION_NOTES`, hito 6.4).
- **Terminología / negación / lateralidad**: reutilizadas tal cual del
  benchmark ASR (`benchmark/metrics/`), sobre el texto aplanado del
  contenido generado.
- **Fact preservation / hallucination**: nuevas (`metrics.py`),
  presencia de `required_facts`/`forbidden_facts` declarados.
- **Numeric accuracy**: nueva, mismo principio de patrón
  correcto/incorrecto explícito que negación/lateralidad.
- **Missing information completeness**: nueva, ¿se señalaron los
  `expected_missing_topics` declarados?
- **Evidence coverage**: nueva, `null` en el alcance de 6.2 (ver arriba).
- **Latencia / tokens / coste**: medidos directamente en el runner.

## 5. `PATIENT_SUMMARY` — precondición de dominio

`AIArtifactType.PATIENT_SUMMARY` se cerró como contrato de dominio en
este hito (RFC §4.3 lo define suficientemente: `{"text": str}`, misma
forma que `SUMMARY`). Cambios: enum en `entities.py`, validador en
`schemas.py`, **nunca** añadido a `PIPELINE_STEP_ORDER` ni al catálogo de
`service.py` — sin `PipelineStep`, sin cambio de comportamiento en
producción. Ver `test_generation_benchmark_isolation.py`.

## 6. Gates clínicos (jerárquicos, RFC §21-22)

Un modelo barato no puede compensar un error clínico crítico con mejores
resultados en otra dimensión:

1. **GATE 1** — 0 violaciones de seguridad (`SafetyValidator`).
2. **GATE 2** — 0 alucinaciones críticas (`forbidden_facts` presentes).
3. **GATE 3** — schema válido.
4. **GATE 4** — negaciones/lateralidad críticas correctas (0 fallos).

Solo tras superar los 4 se comparan completeness/coste/latencia
(`compare.py`). Clasificación de hallazgos CRITICAL/MAJOR/MINOR derivada
estructuralmente de qué categoría falló (RFC §22, ver `gates.py`):
negación/lateralidad/hallazgo prohibido/safety → CRITICAL; hecho omitido
→ MAJOR; diferencia de terminología → MINOR.

## 7. OpenRouter

Verificado el 2026-08-11 contra `https://openrouter.ai/docs/api-reference/overview`,
`https://openrouter.ai/docs/features/structured-outputs` y
`https://openrouter.ai/api/v1/models`:

- Endpoint: `POST https://openrouter.ai/api/v1/chat/completions`.
- Auth: cabecera `Authorization: Bearer <OPENROUTER_API_KEY>`.
- Cuerpo: `model`, `messages` (`system`/`user`), `temperature`,
  `max_tokens`, `response_format` opcional para structured output
  (`{"type": "json_schema", "json_schema": {"name", "strict", "schema"}}`).
- Uso/coste en la respuesta: `usage.prompt_tokens`,
  `usage.completion_tokens`, `usage.cost` (coste autoritativo del
  proveedor, cuando está disponible).
- Errores HTTP estándar; `429` = rate limited.

`BenchmarkLLMClient` (`openrouter_client.py`) implementa exactamente este
contrato. **Nunca confía en que el proveedor cumplió el schema**: toda
respuesta pasa igualmente por `validate_content_schema` (encargo §14).

## 8. Modelos candidatos (verificado 2026-08-11)

| Familia | Model id (OpenRouter) | Contexto | Structured output | Precio input /1M | Precio output /1M |
|---|---|---|---|---|---|
| Anthropic | `anthropic/claude-sonnet-5` | 1M | Sí (confirmado) | $2.00 | $10.00 |
| Anthropic | `anthropic/claude-opus-5` | 1M | Sí (confirmado) | $5.00 | $25.00 |
| OpenAI | `openai/gpt-5.2` | 400K | No confirmado — revisar `supported_parameters` antes de usar `response_json_schema` | $1.75 | $14.00 |
| Google | `google/gemini-3.6-flash` | 1M | Sí (confirmado) | $1.50 | $7.50 |

Fuente: JSON público `openrouter.ai/api/v1/models` (campo `pricing`,
USD/token) más la página individual de cada modelo, cruzados con
resultados de búsqueda independientes coincidentes. Tabla real en
`benchmark/generation/pricing.py` (`MODEL_PRICING`), `PRICING_VERSION =
"2026-08-11.1"`. Nunca facturación autoritativa — el coste real de
`usage.cost` siempre tiene prioridad (`CostEstimateSource.PROVIDER`) sobre
esta tabla.

## 9. Prompts

`benchmark/generation/prompts.py` — 3 `PromptCandidateSpec` (una por
`artifact_type`), sembradas vía `PromptTemplateRepository` (misma
infraestructura que producción, nunca prompts hardcodeados en el
runner):

```bash
python -m benchmark.generation.seed_prompts
```

Idempotente: una plantilla activa por `(artifact_type, language)`, nunca
sobreescrita en silencio (mismo invariante que 6.0.5). Contenido alineado
con `clinical-safety.md` §2-3; el texto no confiable (transcripción,
resumen) solo ocupa variables del `user_prompt_template`, nunca el
`system_prompt`.

## 10. Ejecutar el benchmark

```bash
docker compose exec backend python -m benchmark.generation.seed_prompts
docker compose exec backend python -m benchmark.generation.cli \
  consulta_ficticia_01__summary --models anthropic/claude-sonnet-5,google/gemini-3.6-flash
docker compose exec backend python -m benchmark.generation.compare \
  consulta_ficticia_01__summary consulta_ficticia_01__missing_information \
  consulta_ficticia_01__patient_summary
```

Requiere `GENERATION_BENCHMARK_ENABLED=true` y `OPENROUTER_API_KEY`
configuradas — falla explícitamente si faltan. Ejecución **secuencial**
(encargo §17), nunca concurrente.

## 11. Resultados

```
benchmark/generation_results/
  <model_profile>/<case_id>.json       # provider/model resueltos como "provider__model"
  comparisons/<case_id>.json
  comparisons/summary.json               # solo con >1 case_id — ver §12
```

No versionados (`.gitignore`), a diferencia del dataset. Esquema completo
en `report.py::build_result` — nunca incluye API key, cabeceras ni el
prompt renderizado completo (solo `template_id`/`template_version`).

## 12. Selección de ganador

`compare.py` nunca fuerza un único ganador global. Por `case_id`
(=`artifact_type`): entre los modelos que superan los 4 gates, gana quien
tenga menos hallazgos MAJOR y, en empate, menor coste. Con varios
`case_id` en la misma invocación, `summary.json` declara `global_winner`
**solo** si el mismo modelo gana en los tres `artifact_type`; si no,
`global_winner` es `null` y `winners_by_artifact_type` muestra el
desglose real — un modelo puede ganar en `summary` y perder en
`missing_information`.

## 13. Cómo añadir un caso nuevo

Ver `backend/benchmark/generation_dataset/README.md`.

## 14. Cómo añadir un modelo nuevo

1. Confirma el model id exacto y el precio vigente en
   `https://openrouter.ai/api/v1/models` (nunca de memoria).
2. Añade una entrada a `MODEL_PRICING` en `pricing.py` (o deja que
   `usage.cost` de la respuesta se use directamente si el modelo lo
   reporta — no siempre hace falta la tabla).
3. Pásalo a `--models` en `cli.py`. Ningún otro fichero cambia.

## 15. Cómo interpretar resultados

- `gates.passed_all: false` con `blocking_gate` distinto de `null` →
  descarta el modelo para ese `artifact_type`, sin importar coste/latencia.
- `findings` con `severity: "critical"` → nunca aceptable en producción,
  independientemente de cuántos `minor` tenga otro modelo.
- `validation.grounding_valid: null` → esperado en el alcance actual (§4),
  no es un fallo.
- `execution.cost_source: "unknown"` → el modelo no está en
  `MODEL_PRICING` y OpenRouter no reportó `usage.cost`; el coste real
  sigue sin conocerse, no se muestra como `0`.
