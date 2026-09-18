"""Bloqueo de dominios de email desechables/temporales en el alta pública
de clínica (Fase 12, hito 12.4 ampliado, decisión del 2026-09-18 — ver
docs/fase-12-rfc.md §6).

Segunda capa de anti-abuso, distinta de Turnstile: Turnstile filtra
scripts/bots genéricos, pero no impide que una persona real use
deliberadamente un email de usar-y-tirar para crear cuentas de prueba
repetidas (el propio Gerard ha visto este patrón de abuso desde el otro
lado, en el mundo del reselling de sneakers). Un dominio desechable no es
en sí mismo prueba de mala fe, pero no tiene sentido en el contexto de
`admin_email` (el email de contacto real de una clínica que va a recibir
facturación/soporte), así que se rechaza directamente en vez de intentar
distinguir intención.

Lista estática y curada (no exhaustiva) de los proveedores de email
desechable más conocidos/usados, en vez de una dependencia de terceros
(p. ej. el paquete `disposable-email-domains` de PyPI): mismo criterio que
`AUDIOLOGY_KEYTERMS_ES` (app/integrations/keyterms.py) — datos estáticos
embebidos en el propio código, sin una fuente externa que mantener
actualizada por su cuenta. Extender esta lista es tan simple como añadir
una entrada más; no se pretende cubrir el 100% de los proveedores
existentes, solo elevar el coste de abuso casual."""

from __future__ import annotations

#: Dominios en minúsculas, sin subdominios (se compara contra la parte
#: tras el `@`, ya normalizada por `normalize_email`).
DISPOSABLE_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "mailinator.com",
        "guerrillamail.com",
        "guerrillamail.info",
        "guerrillamail.biz",
        "guerrillamail.org",
        "guerrillamail.net",
        "guerrillamail.de",
        "sharklasers.com",
        "10minutemail.com",
        "10minutemail.net",
        "20minutemail.com",
        "temp-mail.org",
        "tempmail.com",
        "tempmail.net",
        "tempmailo.com",
        "throwawaymail.com",
        "yopmail.com",
        "yopmail.net",
        "yopmail.fr",
        "trashmail.com",
        "trashmail.net",
        "fakeinbox.com",
        "getnada.com",
        "maildrop.cc",
        "mintemail.com",
        "mohmal.com",
        "mytemp.email",
        "dispostable.com",
        "moakt.com",
        "spamgourmet.com",
        "discard.email",
        "discardmail.com",
        "emailondeck.com",
        "burnermail.io",
        "inboxbear.com",
        "tempinbox.com",
        "mailnesia.com",
        "mailcatch.com",
        "mail-temporaire.fr",
        "correotemporal.org",
        "emailtemporal.org",
        "correotemporal.com",
    }
)


def is_disposable_email_domain(email: str) -> bool:
    """`email` se asume ya normalizado (minúsculas, sin espacios) por
    `normalize_email` — pero es defensivo ante no estarlo, dado que puede
    llamarse de forma independiente."""
    _, _, domain = email.strip().lower().rpartition("@")
    return domain in DISPOSABLE_EMAIL_DOMAINS
