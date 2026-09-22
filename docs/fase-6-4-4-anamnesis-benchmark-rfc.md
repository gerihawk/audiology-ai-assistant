# RFC — Benchmark de generación para ANAMNESIS y SESSION_NOTES (hito 6.4.4)

**Estado (2026-09-22): decisiones de §7 confirmadas, dataset de 2 casos
para ANAMNESIS y 2 casos para SESSION_NOTES completos, benchmark ejecutado
contra los 4 candidatos para los dos `artifact_type` — ver §8 (ANAMNESIS,
2026-09-21) y §9 (SESSION_NOTES, 2026-09-22) para los resultados.** La
infraestructura de medición (métrica `evaluate_field_status_match`,
GATE 2/GATE 4 en `gates.py`, clasificación crítico/no-crítico en
`benchmark/generation/field_criticality.py`) está implementada y
cubierta por tests (`test_generation_benchmark_metrics.py`,
`test_generation_benchmark_gates.py`, `test_generation_field_criticality.py`).
Prompts candidatos (`anamnesis_es_v1.md`/`session_notes_es_v1.md`) publicados
en `app/ai_pipeline/prompts/` y sembrados en BD. Pendiente: ampliar el
dataset de ANAMNESIS y/o SESSION_NOTES más allá de los 2 casos iniciales de
cada uno si hace falta más señal para elegir un ganador definitivo, y la
activación en producción (§6, hito posterior una vez haya ganador).

Propuesta de diseño para cerrar el hueco que `fase-6-rfc.md` §11.1 dejó
abierto deliberadamente: `ANAMNESIS`/`SESSION_NOTES` siguen en `Mock`
porque, a diferencia de `SUMMARY`/`PATIENT_SUMMARY`/`MISSING_INFORMATION`
(benchmark del hito 6.2, ver [generation-benchmark.md](generation-benchmark.md)),
son contenido **estructurado y con evidencia obligatoria** (20 campos con
`{value, status, source_excerpt}` para `ANAMNESIS`; 4 bloques con `{text,
source_excerpt}` para `SESSION_NOTES`), no texto libre. Necesitan su
propio criterio de evaluación antes de poder comparar proveedores con
datos, no solo reutilizar las métricas de 6.2 tal cual.

Este documento no implementa nada — es la ronda de decisiones de diseño
previa, mismo criterio que `fase-13-rfc.md` antes de escribir código de
facturación. Auditoría entre fases del 2026-09-21: candidato 1, elegido
por Gerard junto con el checklist "antes del primer cliente" (candidato 2)
y la facturación consolidada Cadena/Empresa (candidato 3, sin empezar
todavía).

## 1. Lo que ya está resuelto y no hay que rediseñar

- **Grounding real, no un no-op** (a diferencia de 6.2 — ver
  `generation-benchmark.md` §4): `_build_source_map`
  (`app/ai_pipeline/domain/validation_pipeline.py`) ya recorre
  genéricamente cualquier nodo con `source_excerpt` y rechaza la
  generación entera (`GROUNDING_FAILED`, con reintento) si una cita no
  aparece literalmente en el transcript. Esto **ya corre en producción
  hoy**, incluso en `Mock` — no es algo que el benchmark tenga que
  añadir, solo algo que hereda gratis.
- **Consistencia evidencia/estado**, ya validada estructuralmente por
  `schemas.py` (`_check_anamnesis_evidence_consistency`/
  `_check_session_notes_evidence_consistency`): `informado`/
  `negado_explicitamente` exigen `source_excerpt` no vacío;
  `no_preguntado`/`no_determinado`/bloque vacío exigen `source_excerpt
  = None`. Un modelo no puede inventar una cita para un campo sin
  evidencia sin que el schema lo rechace.
- **Formato del dataset — sin cambios**: `input.json`/`reference.json`/
  `metadata.json` (generation-benchmark.md §3) ya sirven tal cual.
  `reference.json.content` para `ANAMNESIS`/`SESSION_NOTES` es
  exactamente el mismo schema cerrado que produce el modelo — la
  referencia humana de Gerard, campo por campo, ES la verdad de
  referencia que necesita el benchmark. No hace falta inventar un
  formato nuevo.
- **`applies_to()` y targeting** (hito 6.4.2, ya implementado en
  `AnamnesisStep`/`SessionNotesStep`) — fuera del alcance de este RFC,
  no cambia.

## 2. Lo que sí es nuevo: qué mide el benchmark

Como el grounding estructural ya bloquea la fabricación de una cita
falsa, el riesgo real que el benchmark tiene que detectar **no es** "¿se
inventó una cita?" (ya cubierto) sino dos categorías más sutiles, campo a
campo (o bloque a bloque):

1. **Fabricación de estado** (`status_escalation`): el modelo marca
   `informado`/`negado_explicitamente` con una cita real del transcript,
   pero esa cita no responde de verdad a lo que ese campo de anamnesis
   pregunta (p. ej. una mención tangencial de "ruido" en el trabajo
   marcada como respuesta a `exposicion_ruido` cuando en realidad el
   paciente hablaba de otra cosa). El grounding estructural no lo
   detecta —una cita real existe— pero la referencia humana de Gerard sí
   sabe si esa cita es válida para ese campo.
2. **Omisión** (`status_downgrade`): el modelo marca
   `no_preguntado`/`no_determinado` (o bloque vacío) cuando la referencia
   dice que el paciente sí aportó esa información. Clínicamente tan
   grave como fabricar un dato — un síntoma real que desaparece del
   borrador nunca llega al profesional.

Métrica principal, nueva (`benchmark/generation/metrics.py`, misma
ubicación que `evaluate_forbidden_facts`): `evaluate_field_status_match`
— compara, campo por campo (`ANAMNESIS`) o bloque por bloque
(`SESSION_NOTES`), el `status` generado contra el de referencia.
Resultado por campo: `match` / `status_escalation` / `status_downgrade`
(nunca "parcial" — el status es un enum cerrado de 4 valores, la
comparación es exacta). Devuelve un `FieldMatchReport` con la lista
completa, no solo un porcentaje agregado — igual que
`HallucinationReport` ya expone `forbidden_facts_found`, no solo un
booleano.

Métrica secundaria (solo quality, nunca gate): comparación de texto
libre (`value`/`text`) entre generado y referencia SOLO en los campos
donde el `status` coincide y es `informado`/`negado_explicitamente` —
mismo tipo de comparación por subcadenas/patrones que ya usa
`terminology`/`negation`/`laterality` en el benchmark ASR, no LLM-as-judge.

## 3. Gates propuestos (jerárquicos, mismo criterio que generation-benchmark.md §6)

1. **GATE 1** — 0 violaciones de seguridad (`SafetyValidator`, sin cambio).
2. **GATE 2** — 0 campos en `status_escalation` sobre un campo marcado
   como **crítico** (ver §4 — clasificación pendiente de que Gerard la
   confirme). Fabricar información sobre un campo crítico es la
   alucinación clínica de este `artifact_type`, equivalente a
   `forbidden_facts` en 6.2.
3. **GATE 3** — schema válido (sin cambio, ya estructural).
4. **GATE 4 — propuesta nueva, pendiente de confirmar con Gerard**: 0
   campos en `status_downgrade` sobre un campo crítico. Esto es una
   decisión clínica, no técnica — ¿omitir un síntoma real que el
   paciente reportó debe **descalificar** al modelo (gate) o solo
   penalizar el ranking (finding MAJOR)? La propuesta de este RFC es que
   sí sea gate para los campos marcados críticos en §4, por el mismo
   motivo que North Star del proyecto ("nunca ocultar una señal real
   requiere valoración profesional") — pero es una decisión que debe
   confirmar Gerard, no que yo decida solo.

Campos no críticos: `status_escalation`/`status_downgrade` sobre ellos
son findings MAJOR (no gate) — penalizan el ranking igual que cualquier
otro MAJOR de 6.2, sin descalificar al modelo.

## 4. Propuesta de clasificación de campos críticos (a confirmar/editar por Gerard)

Solo los campos marcados aquí como **crítico** participan en los GATE
2/4 de arriba; el resto son MAJOR. Propuesta inicial basada en qué
información cambiaría la valoración de un profesional si se fabricara u
omitiera — **Gerard es quien debe confirmar o corregir esta lista**, es
juicio clínico, no técnico:

| Campo | Propuesta |
|---|---|
| `tinnitus` | crítico |
| `vertigo_o_inestabilidad` | crítico |
| `otalgia` | crítico |
| `otorrea` | crítico |
| `medicacion_ototoxica_declarada` | crítico |
| `antecedentes_otologicos` | crítico |
| `cirugias` | crítico |
| `lateralidad` | crítico |
| `infecciones` | crítico |
| `motivo_consulta` | crítico |
| `percepcion_subjetiva_perdida_auditiva` | no crítico |
| `inicio_y_evolucion` | no crítico |
| `antecedentes_familiares` | no crítico |
| `exposicion_ruido` | no crítico |
| `sensacion_plenitud` | no crítico |
| `dificultades_comprension` | no crítico |
| `situaciones_auditivas_problematicas` | no crítico |
| `uso_previo_audifonos` | no crítico |
| `expectativas` | no crítico |
| `impacto_social_laboral_familiar` | no crítico |

Para `SESSION_NOTES` (4 bloques), propuesta: `device_adjustments` y
`patient_reported_issues` críticos (cambios en el dispositivo y
problemas reportados por el paciente son información de seguimiento
clínico directo); `changes_since_last_visit`/`next_steps` no críticos.

## 5. Dataset — qué necesita aportar Gerard

Con el formato ya resuelto (§1), lo único pendiente es contenido: casos
ficticios nuevos en `backend/benchmark/generation_dataset/`, carpeta
`<transcript_id>__anamnesis/` y `<transcript_id>__session_notes/` (puede
reutilizarse el mismo `transcript_id`/transcript que uno ya existente de
6.2 si el caso encaja, o ser nuevos). Por caso:

- `input.json`: transcript ficticio (puede ser el mismo que ya exista
  para `summary` de ese `transcript_id`, si aplica) + `artifact_type`.
- `reference.json`: el `content` completo — los 20 campos de anamnesis
  (o los 4 bloques de session_notes) con su `value`/`status`/
  `source_excerpt` "correctos" tal y como los rellenaría Gerard como
  profesional revisando esa transcripción. Esto es exactamente el
  trabajo más costoso — igual de exigente que definir `reference.json`
  para `summary` en 6.2, pero con 20 campos en vez de un párrafo.

Propuesta de alcance para arrancar: **2 casos** (no los 6+ de 6.2) — uno
con anamnesis "rica" (paciente que aporta mucha información) y uno con
anamnesis "pobre" (paciente que apenas responde, muchos campos
`no_preguntado`/`no_determinado` legítimos) para forzar que el benchmark
distinga bien fabricación de omisión en ambos extremos. Se puede ampliar
después si los resultados no son concluyentes, mismo patrón que 6.2 (que
arrancó con el dataset mínimo y lo fue ampliando).

## 6. Fuera de alcance de este incremento

- Modelos/proveedores candidatos: se reutiliza la misma tabla de
  `generation-benchmark.md` §8 (Claude Sonnet 5/Opus 5, GPT-5.2, Gemini
  3.6 Flash) — sin cambios, no hace falta volver a decidir esto.
- Prompts: nuevos `PromptCandidateSpec` para `ANAMNESIS`/`SESSION_NOTES`
  en `benchmark/generation/prompts.py` — se escriben una vez cerrado este
  RFC, alineados con `clinical-safety.md` §2-3 igual que los tres ya
  existentes.
- Activación en producción (`LLM_PROVIDER_ANAMNESIS`/
  `LLM_MODEL_ANAMNESIS`, `LLM_PROVIDER_SESSION_NOTES`/
  `LLM_MODEL_SESSION_NOTES`, factorías en `service.py`): hito posterior,
  una vez el benchmark tenga un ganador con datos, mismo patrón que
  6.2 → 6.3.

## 7. Decisiones que Gerard debe cerrar antes de que se escriba código

1. ¿Confirma la clasificación crítico/no-crítico de §4, o la corrige?
   **Confirmada sin cambios (2026-09-21).**
2. ¿Confirma que `status_downgrade` sobre un campo crítico debe ser GATE
   (descalifica al modelo), no solo finding MAJOR (§3, GATE 4)?
   **Confirmado: es GATE (2026-09-21).**
3. ¿Empezamos con 2 casos ficticios (uno rico, uno pobre) como propone
   §5, o prefiere otro número/otro enfoque?
   **Confirmado: 2 casos (2026-09-21).**

## 8. Resultados de la primera ejecución real (2026-09-21)

Ejecutado `benchmark/generation/cli.py` contra los 2 casos de `ANAMNESIS`
(`consulta_ficticia_anamnesis_rica__anamnesis`,
`consulta_ficticia_anamnesis_pobre__anamnesis`) y los 4 candidatos de
`generation-benchmark.md` §8 (Claude Sonnet 5, Claude Opus 5, GPT-5.2,
Gemini 3.6 Flash). `SESSION_NOTES` queda fuera de este round (§5).

**Infraestructura — `LLM_MAX_OUTPUT_TOKENS_ESTIMATE` insuficiente.** En el
primer intento, Claude Sonnet 5, Claude Opus 5 y Gemini 3.6 Flash
truncaban la respuesta del caso rico (`invalid_response_format`).
Causa: `llm_max_output_tokens_estimate` (`app/core/config.py`) — compartido
con el pipeline de producción, no solo el benchmark — estaba en 2000 sin
pasarela `docker-compose`/`.env`, insuficiente para el JSON de 20 campos de
`ANAMNESIS` (los otros 3 `artifact_type` de 6.3 son más cortos). Se añadió
la variable a `docker-compose.yml` (commit `65f5ae0`) y se subió a 8000 en
el `.env` local de Gerard; con eso los 4 modelos completan sin
truncamiento.

**Hallazgo de diseño — `antecedentes_otologicos` vs `infecciones`/`cirugias`.**
Con el token cap resuelto, los 4 modelos fallaban el GATE 4 del caso rico
por el mismo motivo exacto: `status_downgrade` crítico en
`antecedentes_otologicos` (lo dejaban vacío). Causa raíz: el
`system_prompt` de `anamnesis_es_v1.md` definía ese campo como "distinto
de infecciones y cirugías (que se recogen aparte)", mientras que
`reference.json` lo trata como un campo que SÍ debe incluir esa
información — contradicción entre el prompt y el criterio clínico de
referencia, no un fallo de los modelos (los 4 seguían la instrucción del
prompt correctamente). Corregido el punto 6 del prompt (commit `1477571`)
para que `antecedentes_otologicos` incluya explícitamente infecciones/
cirugías previas cuando se mencionen, además de en su campo específico.

**Resultado final** (tras las dos correcciones anteriores):

| Modelo | Caso pobre | Caso rico |
|---|---|---|
| Claude Sonnet 5 | limpio (gates OK, 0 findings) | limpio (gates OK, 0 findings) |
| Claude Opus 5 | limpio | limpio |
| GPT-5.2 | GATE OK, 1 MAJOR (`status_escalation` no crítico en `inicio_y_evolucion`) | limpio |
| Gemini 3.6 Flash | GATE OK, mismo MAJOR que GPT-5.2 | limpio |

Ningún modelo se descalifica con el dataset actual. El MAJOR compartido por
GPT-5.2/Gemini en `inicio_y_evolucion` (fabrican `informado` cuando la
referencia dice `no_determinado`) confirma que el caso "pobre" detecta lo
que se diseñó a detectar: la tentación de fabricar contenido sobre una
respuesta ambigua del paciente ("no sabría decirle, igual desde hace
tiempo").

Con solo 2 casos la muestra es pequeña para elegir un ganador definitivo
— ver §5/parte pendiente arriba sobre ampliar el dataset si hace falta más
señal antes de decidir. Activación en producción sigue fuera de alcance de
este incremento (§6).
## 9. Resultados de la ejecución de SESSION_NOTES (2026-09-22)

Ejecutado `benchmark/generation/cli.py` contra los 2 casos nuevos de
`SESSION_NOTES` (`consulta_ficticia_seguimiento_rica__session_notes`,
`consulta_ficticia_seguimiento_pobre__session_notes` — continuación
ficticia de los mismos pacientes de ANAMNESIS, en una sesión de ajuste de
audífono) y los mismos 4 candidatos de `generation-benchmark.md` §8. Sin
incidencias de infraestructura esta vez (el `LLM_MAX_OUTPUT_TOKENS_ESTIMATE`
subido a 8000 en la ronda de ANAMNESIS ya cubre también SESSION_NOTES, 4
bloques es un JSON más corto que los 20 campos de anamnesis).

**Resultado:**

| Modelo | Caso pobre | Caso rico |
|---|---|---|
| Claude Sonnet 5 | GATE OK, 1 MAJOR (`status_escalation` no crítico en `next_steps`) | limpio (gates OK, 0 findings) |
| Claude Opus 5 | **GATE FALLA** (`status_escalation` crítico en `patient_reported_issues` + 2 MAJOR) | limpio |
| GPT-5.2 | **GATE FALLA** (mismo patrón exacto que Opus 5) | limpio |
| Gemini 3.6 Flash | **GATE FALLA** (mismo patrón exacto que Opus 5/GPT-5.2) | limpio |

**Diagnóstico — no es alucinación de hechos, es una interpretación distinta
de "bloque abordado".** El grounding se mantiene intacto en los 4 modelos
(`evidence_coverage.coverage = 1.0` en todos los resultados, incluidos los
3 que fallan el gate): cada `source_excerpt` que citan es una cita literal
real de la transcripción, nunca inventada. El fallo es semántico: ante una
respuesta vaga o evasiva del paciente ("No sé, no me fijo mucho en esas
cosas" para `patient_reported_issues`; "Muy bien, ya nos iremos viendo"
para `next_steps`), 3 de los 4 modelos redactan un `text` parafraseando esa
no-respuesta ("el paciente no refiere ninguna molestia...") y lo marcan
como `reported`, mientras que el criterio de referencia de Gerard es que
una respuesta sin información real deja el bloque `not_reported` (`text=
""`) — igual que se dejó `inicio_y_evolucion` en el caso pobre de ANAMNESIS
(§8) ante una respuesta igual de vaga ("no sabría decirle, igual desde hace
tiempo"). Claude Sonnet 5 es el único que acierta los dos bloques
críticos del caso pobre (`device_adjustments`/`patient_reported_issues`);
falla un único MAJOR no crítico en `next_steps`, no bloqueante.

A diferencia del hallazgo de `antecedentes_otologicos` en la ronda de
ANAMNESIS, aquí no hay ninguna contradicción de instrucciones entre el
`system_prompt` de `session_notes_es_v1.md` (ya dice explícitamente "Si la
transcripción de hoy NO aborda ese bloque, 'text' es ''") y el criterio de
referencia — es exactamente el comportamiento que el caso "pobre" se
diseñó para detectar (§5): la tentación de un modelo de fabricar contenido
a partir de una respuesta ambigua del paciente, en vez de reconocer que no
hay nada sustantivo que reportar.

**Con solo 2 casos por `artifact_type` la muestra sigue siendo pequeña**
(mismo comentario que §8 para ANAMNESIS), pero Claude Sonnet 5 es, con los
datos actuales, el único modelo limpio en los 4 casos combinados
(2 ANAMNESIS + 2 SESSION_NOTES). Activación en producción sigue fuera de
alcance de este incremento (§6).
