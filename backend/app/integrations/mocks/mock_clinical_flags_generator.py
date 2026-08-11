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

#: Caracteres de contexto a cada lado del match para construir el
#: `source_excerpt` real — ver docs/fase-6-rfc.md §4.4.
_EXCERPT_PADDING = 60

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


def _build_excerpt(transcript: str, lowered: str, keywords: tuple[str, ...]) -> str:
    """Ventana real de contexto alrededor de la(s) coincidencia(s) que
    dispararon la regla — nunca `transcript[:200]` decorativo. Cubre desde
    el inicio de la primera keyword encontrada hasta el final de la
    última, con `_EXCERPT_PADDING` caracteres de margen a cada lado."""
    matches = [
        (idx, idx + len(keyword)) for keyword in keywords if (idx := lowered.find(keyword)) != -1
    ]
    start = min(m[0] for m in matches)
    end = max(m[1] for m in matches)
    window_start = max(0, start - _EXCERPT_PADDING)
    window_end = min(len(transcript), end + _EXCERPT_PADDING)
    return transcript[window_start:window_end]


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
                        source_excerpt=_build_excerpt(transcript, lowered, keywords),
                        ruleset_name=RULESET_NAME,
                    )
                )
                seen_categories.add(category)
        return flags
