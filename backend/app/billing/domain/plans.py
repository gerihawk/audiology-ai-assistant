"""Niveles de precio cerrados en docs/fase-13-rfc.md §3.2 (decisión del
2026-09-18). Un slug estable por nivel — nunca el nombre comercial
directamente (ese puede cambiar en el frontend sin tocar backend/Stripe).
"""

from __future__ import annotations

from enum import StrEnum

from app.core.config import Settings


class Plan(StrEnum):
    """Mismo patrón que `IntegrationName`
    (app/integrations/domain/integration_config.py): un `StrEnum` usado
    directamente como tipo de campo Pydantic — FastAPI valida y documenta
    los valores permitidos en OpenAPI sin repetir la lista a mano."""

    BASICO = "basico"
    PROFESIONAL = "profesional"
    CLINICA_GRANDE = "clinica_grande"
    CADENA_EMPRESA = "cadena_empresa"


#: Nombre del campo de `Settings` que guarda el Price de Stripe de cada
#: nivel — mismo patrón que `_VENDOR_API_KEY_FIELDS` en app/core/config.py.
_PLAN_PRICE_ID_SETTINGS_FIELD: dict[Plan, str] = {
    Plan.BASICO: "stripe_price_id_basico",
    Plan.PROFESIONAL: "stripe_price_id_profesional",
    Plan.CLINICA_GRANDE: "stripe_price_id_clinica_grande",
    Plan.CADENA_EMPRESA: "stripe_price_id_cadena_empresa",
}


class PlanNotConfiguredError(ValueError):
    """El nivel es válido pero no tiene un Price de Stripe configurado
    todavía (p. ej. STRIPE_PRICE_ID_BASICO ausente en este entorno)."""


def resolve_price_id(settings: Settings, plan: Plan) -> str:
    field_name = _PLAN_PRICE_ID_SETTINGS_FIELD[plan]
    price_id = getattr(settings, field_name)
    if not price_id:
        raise PlanNotConfiguredError(
            f"El nivel '{plan.value}' no tiene un Price de Stripe configurado "
            f"({field_name.upper()})."
        )
    return price_id
