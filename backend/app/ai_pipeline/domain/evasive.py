"""Detección de respuesta evasiva/metacomentario — ver docs/fase-6-rfc.md
§5.1 (paso 3) y Anexo A ("Respuesta 'soy una IA' → evasive_or_meta_response,
retry acotado"). Determinista, sin LLM: un LLM real que se niega a
generar contenido clínico o responde hablando de sí mismo en vez de
completar la tarea no debe persistirse como si fuera un borrador válido.

Misma normalización que `SafetyValidator`/`GroundingValidator` (tildes,
mayúsculas, puntuación, espacios) para no depender de la puntuación exacta
que use un proveedor real."""

from __future__ import annotations

from app.ai_pipeline.domain.content_walk import iter_string_leaves
from app.core.text_normalize import normalize_text

EVASIVE_META_PHRASES: tuple[str, ...] = (
    "soy una ia",
    "soy un modelo de lenguaje",
    "como modelo de lenguaje",
    "como inteligencia artificial",
    "no puedo generar contenido médico",
    "no tengo acceso a",
    "no puedo ayudarte con eso",
)


def detect_evasive_response(content: object) -> bool:
    for _, text in iter_string_leaves(content):
        normalized_text = normalize_text(text)
        if any(normalize_text(phrase) in normalized_text for phrase in EVASIVE_META_PHRASES):
            return True
    return False
