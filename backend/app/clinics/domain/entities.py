"""Entidad de dominio Clinic. Sin dependencias de SQLAlchemy."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Clinic:
    id: uuid.UUID
    name: str
    code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # --- Facturación / Stripe (Fase 13, hito 13.1) — ver docs/fase-13-rfc.md §5 ---
    # `stripe_customer_id`/`stripe_subscription_id` pueden repetirse entre
    # varias filas de `Clinic`: es lo único que necesita el nivel
    # Cadena/Empresa (§3.3) para una facturación consolidada por volumen —
    # sin tabla ni entidad nueva. `None` en los tres hasta que la clínica
    # complete `POST /billing/checkout-session` y el webhook confirme el
    # alta (`checkout.session.completed`).
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    # Valor crudo del `status` de la suscripción de Stripe
    # ("trialing"/"active"/"past_due"/"unpaid"/"canceled"/...) — nunca
    # normalizado a un enum propio: el gate de acceso (hito 13.2) decide
    # qué valores permiten el uso de la plataforma.
    subscription_status: str | None = None
    # Slug del nivel contratado — ver app/billing/domain/plans.py
    # (PLAN_BASICO/PLAN_PROFESIONAL/PLAN_CLINICA_GRANDE/PLAN_CADENA_EMPRESA).
    plan: str | None = None
    # Contador de sesiones del periodo de facturación en curso — usado por
    # el overage medido (hito 13.2, ver BillingService.report_overage_usage).
    sessions_used_this_period: int = 0
    # --- Facturación / Stripe (Fase 13, hito 13.2) ---
    # Inicio del periodo de facturación actual — fijado por
    # `set_billing_fields` (alta) y por `start_new_billing_period`
    # (renovación en cada `invoice.paid`). Es el límite temporal que usa
    # `report_overage_usage` para saber desde cuándo contar ejecuciones del
    # pipeline real: sin esto no habría forma de distinguir "uso de este
    # periodo" de "uso de periodos anteriores ya facturados".
    current_period_started_at: datetime | None = None
    # --- Facturación / Stripe (ampliación 2026-09-21, auditoría entre
    # fases tras el hito 13.3) --- Tope de sesiones incluidas negociado
    # INDIVIDUALMENTE para esta clínica — exclusivo del nivel Cadena/
    # Empresa (docs/fase-13-rfc.md §3.3: precio y condiciones por
    # volumen, negociados caso a caso, nunca un valor global como
    # `PLAN_INCLUDED_SESSIONS` en el resto de niveles). `None` mientras
    # esa clínica no tenga un tope negociado todavía (comportamiento
    # igual que antes de esta ampliación: sin techo, nunca bloquea por
    # uso). Se fija a mano desde el panel de operador de la plataforma
    # (`app.platform_admin`) al negociar el contrato — ver
    # `app/billing/domain/plans.py` para cómo se usa.
    negotiated_included_sessions: int | None = None
