"""Niveles de precio cerrados en docs/fase-13-rfc.md §3.2 (decisión del
2026-09-18). Un slug estable por nivel — nunca el nombre comercial
directamente (ese puede cambiar en el frontend sin tocar backend/Stripe).
"""

from __future__ import annotations

from enum import StrEnum

from app.clinics.domain.entities import Clinic
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
#: negociado directamente (§3.3), sin un tope de sesiones global válido
#: para todas sus clínicas. **Ampliación 2026-09-21** (auditoría entre
#: fases): en vez de eso, cada `Clinic` de este nivel puede llevar su
#: propio tope en `Clinic.negotiated_included_sessions`, fijado a mano
#: por Gerard al negociar el contrato (panel `app.platform_admin`) — ver
#: `included_sessions()`/`safety_cap_sessions()` más abajo, que ahora
#: aceptan la `Clinic` para resolverlo. Mientras esa clínica no tenga un
#: tope negociado todavía, el comportamiento sigue siendo el de antes de
#: esta ampliación: `None`, sin bloqueo por uso. El reporte de overage
#: medido (`BillingService.report_overage_usage`) sigue sin aplicar a
#: este nivel en ningún caso — el tope negociado alimenta solo el gate
#: de acceso, nunca un cobro automático de exceso a Stripe (no hay
#: mecanismo de Price medido por clínica individual, solo por nivel).
PLAN_INCLUDED_SESSIONS: dict[Plan, int] = {
    Plan.BASICO: 40,
    Plan.PROFESIONAL: 150,
    Plan.CLINICA_GRANDE: 400,
}

#: Múltiplo del tope incluido a partir del cual se bloquea el acceso, no
#: solo se cobra overage (docs/fase-13-rfc.md §3.2: "hasta un techo de
#: seguridad fijado en el doble del tope incluido"). Se aplica igual al
#: tope negociado de Cadena/Empresa (ampliación 2026-09-21) — mismo
#: criterio para todos los niveles, nunca uno especial para ese nivel.
SAFETY_CAP_MULTIPLIER = 2


def included_sessions(plan: Plan, clinic: Clinic | None = None) -> int | None:
    """Tope de sesiones incluidas del nivel. Para todos los niveles salvo
    Cadena/Empresa es el valor global de `PLAN_INCLUDED_SESSIONS`, igual
    para cualquier clínica de ese nivel — `clinic` se ignora en ese caso.
    Para Cadena/Empresa (§3.3, ampliación 2026-09-21) devuelve en su
    lugar `clinic.negotiated_included_sessions`: `None` si no se pasa
    `clinic` (para no romper una llamada que solo conocía el `plan`) o si
    esa clínica concreta todavía no tiene un tope negociado."""
    if plan is Plan.CADENA_EMPRESA:
        return clinic.negotiated_included_sessions if clinic is not None else None
    return PLAN_INCLUDED_SESSIONS.get(plan)


def safety_cap_sessions(plan: Plan, clinic: Clinic | None = None) -> int | None:
    """Techo de seguridad = `SAFETY_CAP_MULTIPLIER` × tope incluido —
    misma resolución que `included_sessions()`, incluida la ampliación de
    Cadena/Empresa vía `clinic`. `None` si `included_sessions()` ya
    devuelve `None` (sin tope definido, no se bloquea nunca por uso)."""
    included = included_sessions(plan, clinic)
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
