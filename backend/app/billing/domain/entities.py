"""Entidad de dominio ProcessedWebhookEvent. Sin dependencias de SQLAlchemy.

Registro mínimo de idempotencia (Fase 13, hito 13.1, docs/fase-13-rfc.md
§5/§6): antes de aplicar cualquier evento de `POST /billing/webhook`,
`BillingService` comprueba que su `event_id` no esté ya aquí — Stripe puede
reenviar el mismo evento más de una vez.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ProcessedWebhookEvent:
    event_id: str
    event_type: str
    processed_at: datetime
