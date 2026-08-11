"""Benchmark reproducible de generación LLM — Fase 6.2 (docs/fase-6-rfc.md
§6.2, docs/generation-benchmark.md).

Deliberadamente independiente del pipeline de producción
(`app/ai_pipeline/`): nunca crea `AIArtifact`, nunca toca
`ai_artifacts`/`ai_artifact_versions`/`ai_generation_runs`, y el único
proveedor LLM que conoce (OpenRouter, vía `openrouter_client.py`) no se
usa en ningún punto de `app/`. Reutiliza directamente la validación de
dominio ya existente (`validate_generated_content`, `SafetyValidator`,
`GroundingValidator`, `retry_policy`, `PromptTemplateRepository`,
`PromptRenderer`) — nunca la duplica.
"""

from __future__ import annotations
