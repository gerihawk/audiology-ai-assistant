# Golden dataset — benchmark de generación (Fase 6.2)

Un caso por carpeta bajo `generation_dataset/<case_id>/`. A diferencia del
dataset de transcripción (`benchmark/dataset/`), aquí no hay audio: cada
caso es `(transcript, artifact_type)`.

```
generation_dataset/
  <transcript_id>__<artifact_type>/
    input.json       # transcripción + artifact_type + contexto — versionado
    reference.json      # referencia HUMANA — versionado, nunca generada por IA
    metadata.json          # invariantes clínicas declaradas — versionado
```

Todos los ficheros se versionan (nunca hay binario que excluir aquí, a
diferencia de `benchmark/dataset/*/audio.*`).

## Convención de `case_id`

`<transcript_id>__<artifact_type>` — el mismo transcript ficticio puede
reutilizarse en varias carpetas, una por `artifact_type` evaluado. Ver
`consulta_ficticia_01__summary`, `consulta_ficticia_01__missing_information`,
`consulta_ficticia_01__patient_summary` (mismo transcript que
`benchmark/dataset/consulta_ficticia_01/reference.json`, Fase 5.1).

## `reference.json` pendiente

Un caso con `"content": null` en `reference.json` está **incompleto**:
`GenerationBenchmarkRunner` se niega a invocar un modelo real para él
(`GenerationReferenceRequiredError`). Rellena `content` con la forma
exacta del `artifact_type` (mismo schema que
`app.ai_pipeline.domain.schemas.validate_content_schema`) y quita el
aviso de `notes`.

## Cómo añadir un caso nuevo

1. Crea `generation_dataset/<transcript_id>__<artifact_type>/`.
2. `input.json`: `id`, `language`, `artifact_type`, `transcript`,
   `transcript_segments` (opcional), `context` (variables adicionales
   permitidas, p. ej. `summary_text` para `missing_information`/
   `patient_summary`), `prompt_template` (opcional, por nombre),
   `case_metadata` (libre).
3. `metadata.json`: solo las invariantes relevantes para este
   `artifact_type` — ver `benchmark/generation/case_metadata.py`.
4. `reference.json`: la referencia humana real — nunca generada por un
   LLM. Si todavía no la tienes, dejar `"content": null` y anotarlo en
   `notes`.
5. Verifica que carga: `load_generation_case(Path("generation_dataset"), "<case_id>")`.

Ver docs/generation-benchmark.md para el resto del diseño.
