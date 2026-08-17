"""Textos fijos centralizados (i18n-ready), ver docs/architecture.md §8.

Ningún módulo de dominio ni de API debe escribir estos textos como
literales propios — siempre importan la constante desde aquí.
"""

from __future__ import annotations

#: Regla no negociable #3 de CLAUDE.md — acompaña a toda salida generada
#: por IA, en API y en UI.
AI_DISCLAIMER = (
    "Contenido generado mediante IA. Debe ser revisado y aprobado por un "
    "profesional cualificado antes de incorporarse al expediente."
)

#: docs/clinical-safety.md §7 — obligatorio, además de `AI_DISCLAIMER`,
#: en todo lugar donde se muestren o exporten `clinical_flags` (API, UI,
#: PDF/texto). El checklist que los genera (`MockClinicalFlagsGenerator`)
#: no está validado clínicamente ni es apto para pacientes reales.
RULESET_DISCLAIMER = (
    "Checklist de demostración. No validado clínicamente. " "No apto para uso con pacientes reales."
)
