# CLAUDE.md

Guía para cualquier asistente de IA (Claude Code u otro) que trabaje en este
repositorio. Léela antes de escribir o modificar código.

## Qué es este proyecto

Audiology AI Assistant es una app complementaria para audioprotesistas que
transcribe consultas simuladas y genera borradores de anamnesis/resumen
clínico mediante IA, siempre sujetos a revisión y aprobación humana. Contexto
completo en [docs/product-requirements.md](docs/product-requirements.md) y
[docs/clinical-safety.md](docs/clinical-safety.md).

## Reglas no negociables

1. **Nunca** uses ni generes datos sanitarios reales. Todo paciente, audio o
   transcripción de prueba debe ser ficticio y quedar marcado como tal.
2. **Nunca** redactes contenido generado por IA usando lenguaje diagnóstico
   ("el paciente tiene…", "diagnóstico confirmado", "tratamiento
   recomendado automáticamente"). Usa siempre las expresiones definidas en
   [docs/clinical-safety.md](docs/clinical-safety.md) (p. ej. "señal que
   requiere valoración profesional").
3. Toda salida de IA debe ir acompañada del aviso: *"Contenido generado
   mediante IA. Debe ser revisado y aprobado por un profesional cualificado
   antes de incorporarse al expediente."*
4. **Nunca** inventes valores de anamnesis que no estén en la transcripción.
   Si un campo no se mencionó, su estado es `no_preguntado` o
   `no_determinado`, nunca se rellena con una suposición.
5. **Nunca** guardes secretos, claves o tokens en el repositorio. Solo
   variables de entorno (`.env`, no versionado — usa `.env.example`).
6. **Nunca** llames a una API de pago real. Usa siempre las implementaciones
   `Mock*` de las interfaces de proveedor durante el MVP.
7. **Nunca** ejecutes comandos destructivos (`rm -rf`, `git reset --hard`,
   `docker volume rm` sobre datos existentes, etc.) sin confirmación
   explícita del usuario.
8. **Nunca** hagas commit ni push sin que el usuario lo pida explícitamente
   en ese turno.
9. Respeta la separación entre identidad del paciente y contenido clínico
   descrita en [docs/data-model.md](docs/data-model.md) — no dupliques
   campos identificativos en tablas de contenido clínico.

## Cómo trabajar en este repo

- Fases pequeñas y verificables, alineadas con
  [docs/development-plan.md](docs/development-plan.md). No implementes
  varios módulos a la vez.
- Separación estricta dominio / infraestructura / presentación en el
  backend (ver [docs/architecture.md](docs/architecture.md)).
- Cualquier integración externa (transcripción, LLM, historia clínica,
  calendario) se implementa contra una interfaz abstracta definida en
  `integrations/` o el módulo correspondiente, nunca acoplada directamente.
- Tipado estricto en ambos lados (TypeScript `strict`, type hints Python +
  Pydantic).
- Funciones pequeñas, manejo explícito de errores, sin dependencias
  innecesarias.
- Tests con Pytest para toda lógica de dominio relevante (especialmente
  transiciones de estado de documentos y lógica de anamnesis).
- Formatea con Ruff/Black (Python) y ESLint/Prettier (TypeScript) antes de
  dar por terminada una tarea.
- Cuando exista incertidumbre clínica, legal o de producto, indícalo
  explícitamente en vez de decidir por tu cuenta o inventar una respuesta.

## Estructura de módulos (backend)

`patients`, `clinical_sessions`, `audio`, `transcription`, `anamnesis`,
`session_notes`, `clinical_flags`, `users`, `audit_log`, `integrations`.
Cada módulo mantiene su propio dominio, esquemas Pydantic y capa de
persistencia; evita dependencias circulares entre módulos (ver
[docs/architecture.md](docs/architecture.md)).
