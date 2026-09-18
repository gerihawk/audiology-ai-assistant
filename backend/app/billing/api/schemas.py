"""Schemas Pydantic de /api/v1/billing (Fase 13, hito 13.1)."""

from __future__ import annotations

from pydantic import BaseModel

from app.billing.domain.plans import Plan


class CheckoutSessionRequest(BaseModel):
    plan: Plan


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
