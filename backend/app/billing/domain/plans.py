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


#: Tope de sesiones/mes incluido en cada nivel (docs/fase-13-rfc.md §3.2).
#: Cadena/Empresa NO tiene entrada a propósito: su precio es por volumen
#: negociado directamente (§3.3), sin un tope de sesiones por clínica
#: definido en el RFC — `included_sessions()`/`safety_cap_sessions()`
#: devuelven `None` para este nivel, y tanto el gate de acceso
#: (`BillingService.check_active_subscription`) como el reporte de
#: overage (`BillingService.report_overage_usage`) lo omiten sin aplicar
#: ningún bloqueo ni cobro de exceso. Señalado explícitamente a Gerard:
#: si en el futuro se quiere un tope también para Cadena/Empresa, hace
#: falta una decisión de producto (¿por clínica? ¿agregado de la cadena?)
#: que este RFC no cierra.
PLAN_INCLUDED_SESSIONS: dict[Plan, int] = {
    Plan.BASICO: 40,
    Plan.PROFESIONAL: 150,
    Plan.CLINICA_GRANDE: 400,
}

#: Múltiplo del tope incluido a partir del cual se bloquea el acceso, no
#: solo se cobra overage (docs/fase-13-rfc.md §3.2: "hasta un techo de
#: seguridad fijado en el doble del tope incluido").
SAFETY_CAP_MULTIPLIER = 2


def included_sessions(plan: Plan) -> int | None:
    """`None` para Cadena/Empresa — ver docstring de `PLAN_INCLUDED_SESSIONS`."""
    return PLAN_INCLUDED_SESSIONS.get(plan)


def safety_cap_sessions(plan: Plan) -> int | None:
    """`None` para Cadena/Empresa — sin techo de seguridad definido, el
    gate de acceso nunca bloquea por uso a este nivel (§3.2/§5)."""
    included = PLAN_INCLUDED_SESSIONS.get(plan)
    return included * SAFETY_CAP_MULTIPLIER if included is not None else None


#: Nombre del campo de `Settings` que guarda el Price MEDIDO (metered) de
#: overage de cada nivel — ver docs/fase-13-rfc.md §5. Solo los niveles con
#: tope de sesiones definido tienen overage; Cadena/Empresa queda fuera a
#: propósito (mismo motivo que `PLAN_INCLUDED_SESSIONS`).
_PLAN_METERED_PRICE_ID_SETTINGS_FIELD: dict[Plan, str] = {
    Plan.BASICO: "stripe_metered_price_id_basico",
    Plan.PROFESIONAL: "stripe_metered_price_id_profesional",
    Plan.CLINICA_GRANDE: "stripe_metered_price_id_clinica_grande",
}


def resolve_metered_price_id(settings: Settings, plan: Plan) -> str:
    """Análogo a `resolve_price_id` pero para el Price medido de overage.
    Lanza `PlanNotConfiguredError` tanto si el nivel no tiene overage
    definido (Cadena/Empresa) como si tiene overage pero el Price no está
    configurado en este entorno — en ambos casos el llamador
    (`BillingService.create_checkout_session`) debe tratarlo igual: crear
    la suscripción sin la línea de overage todavía."""
    field_name = _PLAN_METERED_PRICE_ID_SETTINGS_FIELD.get(plan)
    if field_name is None:
        raise PlanNotConfiguredError(
            f"El nivel '{plan.value}' no tiene overage medido definido (docs/fase-13-rfc.md §3.3)."
        )
    price_id = getattr(settings, field_name)
    if not price_id:
        raise PlanNotConfiguredError(
            f"El nivel '{plan.value}' no tiene un Price medido de overage configurado "
            f"({field_name.upper()})."
        )
    return price_id


#: Nombre del campo de `Settings` que guarda el `event_name` del Stripe
#: Billing Meter de cada nivel — objeto DISTINTO del Price medido de
#: arriba (ver docstring de `PaymentGateway.report_overage_usage`): el
#: Price se usa al crear la Checkout Session, el Meter al reportar uso.
_PLAN_METER_EVENT_NAME_SETTINGS_FIELD: dict[Plan, str] = {
    Plan.BASICO: "stripe_meter_event_name_basico",
    Plan.PROFESIONAL: "stripe_meter_event_name_profesional",
    Plan.CLINICA_GRANDE: "stripe_meter_event_name_clinica_grande",
}


def resolve_meter_event_name(settings: Settings, plan: Plan) -> str:
    """Análogo a `resolve_metered_price_id` pero para el `event_name` del
    Meter — usado por `BillingService.report_overage_usage`. Lanza
    `PlanNotConfiguredError` en las mismas condiciones que
    `resolve_metered_price_id`."""
    field_name = _PLAN_METER_EVENT_NAME_SETTINGS_FIELD.get(plan)
    if field_name is None:
        raise PlanNotConfiguredError(
            f"El nivel '{plan.value}' no tiene overage medido definido (docs/fase-13-rfc.md §3.3)."
        )
    event_name = getattr(settings, field_name)
    if not event_name:
        raise PlanNotConfiguredError(
            f"El nivel '{plan.value}' no tiene un Meter de overage configurado "
            f"({field_name.upper()})."
        )
    return event_name
