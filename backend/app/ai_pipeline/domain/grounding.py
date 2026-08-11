"""`GroundingValidator` — primitiva compartida de verificación de evidencia.

Ver docs/fase-6-rfc.md §5.3. Determinista, sin LLM: verifica que un
`source_excerpt` declarado por un campo de un artefacto corresponde
realmente al transcript de la sesión que lo produjo. Reutiliza la
normalización compartida (`app/core/text_normalize.py`, la misma que usa
`benchmark/metrics/text_normalize.py` — ver §5.3) para tolerar
diferencias de mayúsculas, tildes, puntuación y espacios entre el
`source_excerpt` citado y el texto real del transcript.

Primitiva genérica: no sabe qué campos de qué `artifact_type` requieren
evidencia — esa decisión vive en `ai_pipeline/domain/schemas.py` y
`validation_pipeline.py`, que recorren la estructura propia de cada
artefacto (ver §5.3: "la primitiva es genérica, pero cada step recorre su
propia estructura"). No se acepta un fragmento del contexto longitudinal
como grounding actual: solo compara contra el `transcript` recibido.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.text_normalize import normalize_text


@dataclass(slots=True, frozen=True)
class GroundingCheckResult:
    grounded: bool
    #: Offsets en el texto ORIGINAL (sin normalizar) cuando el excerpt
    #: aparece de forma literal en el transcript; `None` si la
    #: coincidencia solo se verificó tras normalizar (tildes/puntuación/
    #: mayúsculas/espacios) o si no se encontró — ver
    #: docs/fase-6-rfc.md §5.4 ("offsets normalizados/originales cuando
    #: pueda resolverse de forma determinista").
    original_start: int | None
    original_end: int | None


def verify_excerpt(excerpt: str, transcript: str) -> GroundingCheckResult:
    """`(excerpt, transcript) -> resultado` — ver docs/fase-6-rfc.md §5.3.

    Un excerpt vacío/solo-espacios o un transcript vacío nunca se
    consideran evidencia válida, aunque `"" in ""` sea técnicamente
    cierto en Python.
    """
    if not excerpt or not excerpt.strip() or not transcript:
        return GroundingCheckResult(grounded=False, original_start=None, original_end=None)

    literal_index = transcript.find(excerpt)
    if literal_index != -1:
        return GroundingCheckResult(
            grounded=True,
            original_start=literal_index,
            original_end=literal_index + len(excerpt),
        )

    normalized_excerpt = normalize_text(excerpt)
    if normalized_excerpt and normalized_excerpt in normalize_text(transcript):
        return GroundingCheckResult(grounded=True, original_start=None, original_end=None)

    return GroundingCheckResult(grounded=False, original_start=None, original_end=None)
