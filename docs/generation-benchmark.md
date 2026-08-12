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
  presencia de `required_facts`/`forbidden_facts` declarados. Para
  `MISSING_INFORMATION` el scope de `forbidden_facts` es distinto al de
  `SUMMARY`/`PATIENT_SUMMARY` — ver recuadro debajo.
- **Numeric accuracy**: nueva, mismo principio de patrón
  correcto/incorrecto explícito que negación/lateralidad.
- **Missing information completeness**: nueva, ¿se señalaron los
  `expected_missing_topics` declarados?

**`MISSING_INFORMATION` — scope de `forbidden_facts` vs. completeness (diagnóstico post-mortem 2026-08-12).**
El contrato de este `artifact_type` es `{"items": [{"topic", "suggested_question"}]}`
— dos campos con función distinta: `topic` declara qué gap afirma el
modelo; `suggested_question` es redacción auxiliar que puede mencionar
legítimamente un concepto ya cubierto al concretar un gap distinto (p.
ej. preguntar "¿en el último año ha tenido inestabilidad?" tras reconocer
"aunque no ha tenido vértigo"). Por eso las dos métricas que leen
`forbidden_facts`/`expected_missing_topics` tienen scopes deliberadamente
distintos:

| Métrica | Scope | Por qué |
|---|---|---|
| `evaluate_forbidden_facts` (falsos positivos / temas ya cubiertos) | **Solo `items[].topic`** (`flatten_missing_information_topics`) | Un patrón de mera presencia sobre `suggested_question` generaba falsos positivos estructurales — mencionar "vértigo" al formular una pregunta de seguimiento no es lo mismo que declararlo missing. |
| `evaluate_missing_information_completeness` (recall) | `topic` + `suggested_question` (sin cambios) | Pregunta distinta: ¿identificó el modelo el gap, en cualquier campo? Restringir a solo `topic` degrada el recall medido cuando el modelo titula el topic de forma abstracta y concreta el gap en la pregunta. |

Un `topic` extra que no matchea ningún `expected_missing_topic` ni ningún
`forbidden_fact` queda **neutral** (no puntuado) en esta versión — no se
penaliza como alucinación ni se premia como recall; ver
`benchmark/generation/metrics.py::flatten_missing_information_topics`.

**`hallucinated clinical fact` vs. `false-positive missing topic`
(diagnóstico post-mortem 2026-08-12, caso real sonnet-5).** Un `topic`
que coincide con un `forbidden_fact` de `MISSING_INFORMATION` **nunca es
la misma categoría de error** que un `forbidden_fact` de
`SUMMARY`/`PATIENT_SUMMARY`, aunque ambos se detecten con la misma
función (`evaluate_forbidden_facts`):

| | Hallucinated clinical fact (`SUMMARY`/`PATIENT_SUMMARY`) | False-positive missing topic (`MISSING_INFORMATION`) |
|---|---|---|
| Qué hace el modelo | Afirma un hecho clínico como cierto (diagnóstico/cirugía/lateralidad inventados). | Propone revisitar un tema que la referencia ya considera suficientemente cubierto — no afirma nada. |
| Ejemplo real | "Hipoacusia neurosensorial confirmada" cuando está pendiente de pruebas. | Topic "Uso de protección auditiva y exposición laboral" cuando el transcript ya cubre 25 años de exposición laboral y uso irregular de protección. |
| Severidad | CRITICAL. | MAJOR. |
| Gate | Bloquea `hallucination_gate` (GATE 2). | No bloquea ningún gate — `hallucination_gate` queda `None` (no aplicable) para `MISSING_INFORMATION`, igual que `negation_laterality_gate` cuando no aplica. |
| `category` del `Finding` | `hallucination`. | `missing_topic_false_positive`. |
| Campo de `MetricsBundle`/`metrics` en el JSON | `hallucination`. | `missing_topic_false_positives` (mismo `HallucinationReport`, reutilizado — nunca arquitectura paralela). |

Implementado en `runner.py::_build_outcome` (el routing según
`artifact_type` decide a qué variable va el resultado de
`evaluate_forbidden_facts`, nunca en `gates.py`/`compare.py`, que no
conocen `artifact_type`) y `gates.py::classify_findings` (rama MAJOR
dedicada). Sigue penalizando calidad — el FP resta en el ranking igual
que cualquier otro MAJOR — solo deja de fingir ser una alucinación
clínica. `SafetyValidator` (seguridad de `suggested_question`) y el
schema gate no se tocan: siguen exactamente igual para los 3
`artifact_type`.
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
2. **GATE 2** — 0 alucinaciones críticas (`forbidden_facts` presentes en
   `SUMMARY`/`PATIENT_SUMMARY`; **no aplica** a `MISSING_INFORMATION` —
   ver "hallucinated clinical fact vs. false-positive missing topic" en
   §4, `hallucination_gate` queda `None` para este `artifact_type`, nunca
   `False`).
3. **GATE 3** — schema válido.
4. **GATE 4** — negaciones/lateralidad críticas correctas (0 fallos).

Solo tras superar los 4 se comparan completeness/coste/latencia
(`compare.py`). Clasificación de hallazgos CRITICAL/MAJOR/MINOR derivada
estructuralmente de qué categoría falló (RFC §22, ver `gates.py`):
negación/lateralidad/hallazgo prohibido (`SUMMARY`/`PATIENT_SUMMARY`)/
safety → CRITICAL; hecho omitido, topic redundante ya cubierto
(`MISSING_INFORMATION`) → MAJOR; diferencia de terminología → MINOR.

**Criterio de desempate único** (fijado en el diagnóstico post-mortem
2026-08-12 — la RFC v2 no prescribe un orden exacto, solo pide medir
"calidad, latencia y coste" y "número de retries"; este es el criterio de
implementación que lo concreta, documentado aquí, no en la RFC):

1. Gates obligatorios — condición de elegibilidad, no desempate.
2. Menor número de hallazgos CRITICAL.
3. Menor número de hallazgos MAJOR.
4. Menor número de hallazgos MINOR (terminología es determinista, no
   estilo humano subjetivo — sí participa en el ranking).

Solo si la calidad clínica determinista es equivalente:

5. Menor número de `attempts` (retries).
6. Menor latencia.
7. Menor coste.

Coste nunca desempata antes que fiabilidad/retries o latencia.
Implementado en `compare.py::build_comparison` — código y documentación
comparten una única fuente de verdad (antes había una discrepancia real
entre el orden que implementaba el código, MAJOR→coste→latencia, y este
criterio; ya resuelta).

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

## 9.5. Generation y evaluation son capas de reproducibilidad separadas

Acordado en el diagnóstico post-mortem de la ronda de benchmark del
2026-08-12: una llamada real a un modelo (**generation run** — prompt,
input, modelo, temperature, `max_output_tokens`, output recibido) y el
cálculo de métricas/gates sobre ese output (**evaluation run**) son dos
capas independientes.

**Cuándo un output puede reevaluarse offline (sin pagar inferencia de nuevo):**
el bug corregido era puramente determinista en post-processing (scoping
de `forbidden_facts` para `MISSING_INFORMATION`) y no cambió prompt,
input, modelo, configuración, ni el output final guardado. Verificación
obligatoria antes de reevaluar offline: confirmar que ningún retry de la
generación original estuvo condicionado por el propio bug — los retries
de `GenerationBenchmarkRunner` dependen únicamente de
`validate_generated_content` (schema/safety/grounding/evasiva), nunca de
`forbidden_facts`/`hallucination` (calculado en `_build_outcome`,
después de que el bucle de reintentos ya ha terminado) — así que ningún
bug de esa métrica puede haber cambiado qué output se conservó.

**Cuándo hay que repetir inferencia:** el bug cambió el prompt, el input,
el modelo/configuración, o pudo haber condicionado qué intento se
conservó entre reintentos (p. ej. un bug que afecte a
`validate_generated_content` sí obligaría a repetir, porque decide qué
attempt sobrevive).

**Versionado:** sin campo explícito de "evaluation version" en el schema
todavía — se documenta en el informe de cada ronda qué versión de código
(commit/estado del working tree) produjo cada evaluación:

- `evaluation_v1` — original, antes de cualquier fix de esta ronda.
- `evaluation_v2` — tras el fix de scoping de `forbidden_facts` para
  `MISSING_INFORMATION` (`topic` únicamente, ver §4).
- `evaluation_v3` — tras el fix de `/` en `text_normalize.py` y de
  `acúfeno` singular en `required_facts` de `SUMMARY` (sin cambio de
  código en la métrica de `forbidden_facts` en sí).
- `evaluation_v4` — tras separar `hallucinated clinical fact` de
  `false-positive missing topic` para `MISSING_INFORMATION` (ver §4):
  mismo mecanismo de detección, pero ya no comparte severidad/gate con
  la alucinación clínica real de `SUMMARY`/`PATIENT_SUMMARY`.

No se ha creado infraestructura nueva de versionado para esto — son
iteraciones deterministas sobre los mismos 12 outputs de
`generation_round_3`, nunca inferencia nueva (ver arriba).

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
