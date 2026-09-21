"""Clasificación crítico/no-crítico de campos de ANAMNESIS y bloques de
SESSION_NOTES para el benchmark de generación — hito 6.4.4.

Confirmada por Gerard el 2026-09-21 sobre la propuesta de
docs/fase-6-4-4-anamnesis-benchmark-rfc.md §4, sin cambios respecto a la
propuesta original.

Es una clasificación exclusiva del *scoring* del benchmark, no un concepto
de producción: decide qué campos participan en los GATE 2/4 de
`gates.py` (fabricación/omisión de un `status` sobre información
clínicamente relevante) frente a cuáles solo generan un finding MAJOR que
penaliza el ranking sin descalificar al modelo. Es juicio clínico de
Gerard, nunca inventado por el asistente (CLAUDE.md regla 4 y "cuando
exista incertidumbre clínica ... indícalo explícitamente en vez de
decidir por tu cuenta")."""

from __future__ import annotations

from app.ai_pipeline.domain.entities import AIArtifactType

#: docs/fase-6-4-4-anamnesis-benchmark-rfc.md §4 — campos cuya fabricación
#: (`status_escalation`) u omisión (`status_downgrade`) cambiaría la
#: valoración de un profesional.
ANAMNESIS_CRITICAL_FIELDS: frozenset[str] = frozenset(
    {
        "motivo_consulta",
        "lateralidad",
        "antecedentes_otologicos",
        "infecciones",
        "cirugias",
        "medicacion_ototoxica_declarada",
        "tinnitus",
        "vertigo_o_inestabilidad",
        "otalgia",
        "otorrea",
    }
)

#: docs/fase-6-4-4-anamnesis-benchmark-rfc.md §4 — cambios de dispositivo y
#: problemas reportados por el paciente son seguimiento clínico directo;
#: `changes_since_last_visit`/`next_steps` quedan fuera (no críticos).
SESSION_NOTES_CRITICAL_BLOCKS: frozenset[str] = frozenset(
    {
        "device_adjustments",
        "patient_reported_issues",
    }
)

CRITICAL_FIELDS_BY_ARTIFACT_TYPE: dict[AIArtifactType, frozenset[str]] = {
    AIArtifactType.ANAMNESIS: ANAMNESIS_CRITICAL_FIELDS,
    AIArtifactType.SESSION_NOTES: SESSION_NOTES_CRITICAL_BLOCKS,
}
