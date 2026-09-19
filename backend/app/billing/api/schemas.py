"""Schemas Pydantic de /api/v1/billing (Fase 13, hitos 13.1/13.2/13.3)."""

from __future__ import annotations

from pydantic import BaseModel

from app.billing.domain.plans import Plan


class CheckoutSessionRequest(BaseModel):
    plan: Plan


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class PortalSessionResponse(BaseModel):
    portal_url: str


class BillingReconcileResponse(BaseModel):
    checked_clinics: list[str]
    reconciled_clinics: list[str]
    overage_reported_clinics: list[str]


class BillingStatusResponse(BaseModel):
    plan: str | None
    subscription_status: str | None
    sessions_used_this_period: int
    included_sessions: int | None
    safety_cap_sessions: int | None
    has_stripe_customer: bool
