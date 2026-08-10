"""MockClinicalFlagsGenerator: checklist basado en reglas, sin LLM.

Heredero directo del antiguo `DemoClinicalFlagRuleset` (ver
docs/ai-pipeline-architecture.md §6.1, §6.4 y §12 decisión 18). No está
validado clínicamente, no es apto para uso con pacientes reales — ver
docs/clinical-safety.md §7.
"""

from __future__ import annotations

from app.integrations.domain.clinical_flags_generator import ClinicalFlagDraft
from app.integrations.domain.session_context import SessionContext

RULESET_NAME = "demo_generic_v1"

#: Coincidencias palabra clave -> señal. Checklist de demostración,
#: deliberadamente simple y determinista (sin IA de por medio).
_KEYWORD_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (
        ("acúfenos", "izquierdo"),
        "tinnitus_unilateral",
        "Acúfenos referidos en un único oído — posible motivo de derivación "
        "según el protocolo configurado.",
    ),
    (
        ("acúfenos", "derecho"),
        "tinnitus_unilateral",
        "Acúfenos referidos en un único oído — posible motivo de derivación "
        "según el protocolo configurado.",
    ),
    (
        ("otalgia",),
        "otalgia",
        "Dolor de oído referido — señal que requiere valoración profesional.",
    ),
    (
        ("otorrea",),
        "otorrea",
        "Secreción de oído referida — señal que requiere valoración profesional.",
    ),
)


class MockClinicalFlagsGenerator:
    async def generate(
        self, transcript: str, *, context: SessionContext
    ) -> list[ClinicalFlagDraft]:
        lowered = transcript.lower()
        seen_categories: set[str] = set()
        flags: list[ClinicalFlagDraft] = []
        for keywords, category, description in _KEYWORD_RULES:
            if category in seen_categories:
                continue
            if all(keyword in lowered for keyword in keywords):
                flags.append(
                    ClinicalFlagDraft(
                        category=category,
                        description=description,
                        source_excerpt=transcript[:200],
                        ruleset_name=RULESET_NAME,
                    )
                )
                seen_categories.add(category)
        return flags
