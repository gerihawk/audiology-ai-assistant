"""Plataforma de benchmark de proveedores de transcripción.

Completamente independiente del AI Pipeline (`app/ai_pipeline/`): no toca
la base de datos, no crea `AIArtifact`, no requiere una sesión clínica
real. Reutiliza únicamente el contrato `TranscriptionProvider` de
`app/integrations/` — ver docs/transcription-benchmark.md.
"""
