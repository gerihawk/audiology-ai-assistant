"""Plantillas de prompt candidatas del benchmark de generación — encargo
de la Fase 6.2 §12-13: "El benchmark debe utilizar la infraestructura
oficial: `PromptTemplateRepository` + `PromptRenderer`. No crear prompts
hardcodeados dentro del runner."

Fuente canónica única (Fase 6.3): `app/ai_pipeline/prompts/` — Git → seed →
BD (docs/fase-6-rfc.md §7.4). Este módulo re-exporta esos mismos objetos
para no romper al resto del paquete `benchmark/`, que sigue importando
`PROMPT_CANDIDATES`/`PromptCandidateSpec`/`seed_prompt_templates` desde
aquí — nunca hay dos cuerpos de prompt independientes. `benchmark/` puede
importar de `app/` (aquí); `app/` nunca importa de `benchmark/`.
"""

from __future__ import annotations

from app.ai_pipeline.prompts.catalog import PROMPT_SOURCES as PROMPT_CANDIDATES
from app.ai_pipeline.prompts.catalog import PromptSourceSpec as PromptCandidateSpec
from app.ai_pipeline.prompts.catalog import seed_prompt_templates

__all__ = ["PromptCandidateSpec", "PROMPT_CANDIDATES", "seed_prompt_templates"]
