# `benchmark/dataset/` — golden dataset

Un caso de benchmark por carpeta. Ver `docs/transcription-benchmark.md`
§Golden dataset para el diseño completo.

```
benchmark/dataset/
  consulta_ficticia_01/
    audio.mp3          # NO versionado (ver .gitignore) — tú lo aportas localmente
    reference.json        # versionado — transcripción manual, fuente de verdad
    metadata.json           # versionado — términos críticos, casos de negación/lateralidad
```

## Cómo añadir un caso nuevo

1. Crea `benchmark/dataset/<id>/` (usa el mismo `<id>` como nombre de carpeta y como `"id"` dentro de `metadata.json`).
2. Copia tu audio ficticio como `benchmark/dataset/<id>/audio.mp3` (o `.wav`/`.m4a`/`.ogg`/`.webm`).
3. Copia `consulta_ficticia_01/reference.json.example` → `<id>/reference.json` y transcribe el audio a mano, segmento por segmento, con el `speaker` correcto.
4. Copia `consulta_ficticia_01/metadata.json.example` → `<id>/metadata.json` y ajusta `critical_terms`/`negation_cases`/`laterality_cases` a lo que realmente contiene tu audio — **nunca inventes casos que el audio no contenga**, invalidaría la métrica.
5. Ejecuta `python -m benchmark.cli <id> --providers mock,assemblyai`.

## Reglas no negociables (CLAUDE.md)

- Solo audios ficticios, grabados con consentimiento de los participantes.
- Nunca pacientes reales, nunca datos sanitarios reales, nunca información identificable.
- `reference.json`/`metadata.json` no contienen audio ni datos personales — son texto y metadatos ficticios, seguros de versionar.

## Almacenamiento local

Solo `reference.json`, `metadata.json`, `*.example` y este `README.md` se
versionan. `audio.*` está excluido por `.gitignore` — cada persona que
ejecute el benchmark aporta sus propios ficheros de audio localmente, sin
que lleguen nunca al repositorio.
