# `benchmark/audio/` — estructura legacy (superada)

**Desde la Fase 5.1, `python -m benchmark.cli`/`python -m benchmark.compare`
ya no leen de aquí — usa `benchmark/dataset/<id>/` en su lugar** (ver
`benchmark/dataset/README.md` y `docs/transcription-benchmark.md` §Golden
dataset): permite asociar cada audio con su `reference.json`/
`metadata.json` y calcular métricas (WER, terminología, negaciones,
lateralidad, diarización), algo que esta carpeta plana no soportaba. Esta
carpeta se conserva sin borrar (no había ningún audio real en ella) solo
como referencia histórica del diseño anterior.

## Reglas no negociables (CLAUDE.md)

- **Solo audios ficticios.** Cualquier fichero que se coloque aquí debe ser
  una grabación simulada (voz de prueba, texto leído, sintetizada, etc.).
- **Nunca pacientes reales.** No se sube, ni temporalmente, ningún audio de
  una consulta real.
- **Nunca datos sanitarios reales.** Ni siquiera anonimizados: el contenido
  hablado debe ser inventado desde el origen, no un caso real con nombres
  cambiados.

## Convención de nombres

`consulta_ficticia_NN_<descripcion-breve>.<extension>`, p. ej.:

```
consulta_ficticia_01_tinnitus.mp3
consulta_ficticia_02_dos_hablantes.wav
```

## Contenido de este directorio

Los ficheros de audio en sí **no se versionan** (ver `.gitignore` en la
raíz del repositorio) — cada persona que ejecute el benchmark localmente
aporta sus propios audios ficticios. Solo este `README.md` se versiona.
