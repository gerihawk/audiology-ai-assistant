"""Normalización y validaciones ligeras del onboarding (Fase 12, hito
12.1) — compartidas entre los esquemas Pydantic de entrada
(`api/schemas.py`, para que un valor inválido devuelva 422 vía el
`RequestValidationError` de Pydantic) y `OnboardingService` (revalidación
defensiva para cualquier llamador que no pase por la API HTTP). Mismo
patrón que `app.patients.domain.normalization`, sin acoplar `onboarding` a
`patients` (módulos sin relación de dominio entre sí).
"""

from __future__ import annotations

#: Sin reglas de complejidad (mayúsculas/símbolos/etc.) — prioriza
#: longitud sobre composición forzada, siguiendo la recomendación NIST
#: 800-63B vigente.
MIN_PASSWORD_LENGTH = 10


def normalize_free_text(value: str) -> str:
    """Recorta y colapsa espacios internos de un campo de texto libre."""
    return " ".join(value.split())


def normalize_required_free_text(value: str, *, field_name: str) -> str:
    normalized = normalize_free_text(value)
    if not normalized:
        raise ValueError(f"{field_name} no puede estar vacío.")
    return normalized


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("Email no válido.")
    return normalized


def validate_password_length(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")
    return password
