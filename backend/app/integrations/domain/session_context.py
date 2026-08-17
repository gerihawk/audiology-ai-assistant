"""Contexto mínimo compartido por los generators del AI Pipeline.

Value object deliberadamente pequeño: en esta fase ningún `Mock*` necesita
más que el identificador de la sesión, pero mantenerlo como su propio tipo
(en vez de pasar un `uuid.UUID` suelto) deja sitio para añadir contexto
adicional en el futuro (p. ej. idioma preferido) sin cambiar la firma de
ninguna interfaz de proveedor.

`session_type` (Fase 6.4.1, RFC técnico §4/§5): el `.value` de
`SessionType` (`clinical_sessions`), NUNCA el propio enum —
`integrations`/`ai_pipeline` no importan vocabulario de otro módulo de
dominio (mismo principio que separa `ClinicalSessionStatus` de
`ProcessingStatus`, ver docs/architecture.md). La conversión ocurre en el
único borde donde `AIPipelineService` ya tiene el `ClinicalSession`
completo. `None` por defecto para no romper ningún constructor existente
(tests/otros módulos que ya construyen `SessionContext` con un solo
argumento) — también el valor real para sesión legacy sin tipo
determinado (docs/fase-6-rfc.md §3.3, "unspecified" en prompts/UI, no en
este value object).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class SessionContext:
    clinical_session_id: uuid.UUID
    session_type: str | None = None
