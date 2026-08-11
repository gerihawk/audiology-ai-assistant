"""Constante compartida de lenguaje clínico prohibido.

Fuente normativa única: docs/clinical-safety.md §3. Producción y tests
importan esta misma constante — ver docs/fase-6-rfc.md §5.2 y §9.1
(prerrequisito 3). Prohibida la duplicación inline en otro punto del
backend o de los tests.

El validador que la aplica en runtime (`SafetyValidator`) es alcance del
hito 6.1 de la Fase 6 — aquí solo se cierra la constante.
"""

from __future__ import annotations

FORBIDDEN_CLINICAL_LANGUAGE: tuple[str, ...] = (
    "el paciente tiene",
    "diagnóstico confirmado",
    "tratamiento recomendado automáticamente",
)
