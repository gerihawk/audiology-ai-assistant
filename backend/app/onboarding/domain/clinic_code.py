"""Generación del `code` de una clínica nueva (Fase 12, hito 12.1).

Nunca elegido libremente por quien se registra — ver docs/fase-12-rfc.md
§5/§6 ("nunca elegido libremente... para evitar enumeración/typosquatting
entre clínicas"). Se deriva del nombre de la clínica (slug determinista) y
`OnboardingService` añade un sufijo aleatorio solo si ese slug ya existe —
ver `app/onboarding/service.py`.
"""

from __future__ import annotations

import re
import unicodedata

#: `ClinicORM.code` es `String(32)` — el sufijo aleatorio (guion + 4
#: caracteres, ver `service.py`) se reserva 5 de esos 32.
_MAX_BASE_LENGTH = 27
_NON_SLUG_CHARS = re.compile(r"[^A-Z0-9]+")


def slugify_clinic_name(name: str) -> str:
    """ "Clínica Auditiva Vila-real" -> "CLINICA-AUDITIVA-VILA-REAL"
    (truncado a `_MAX_BASE_LENGTH`). Nunca vacío: un nombre sin ningún
    carácter alfanumérico (p. ej. solo emoji) cae al valor fijo "CLINICA",
    igual de válido como base para el sufijo aleatorio de `service.py`."""
    # NFKD + descartar los combining marks: quita acentos sin depender de
    # una tabla de sustitución manual (mismo enfoque que
    # `unicodedata.normalize` en la stdlib, sin dependencia nueva).
    ascii_only = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = _NON_SLUG_CHARS.sub("-", ascii_only.upper()).strip("-")
    return slug[:_MAX_BASE_LENGTH].strip("-") or "CLINICA"
