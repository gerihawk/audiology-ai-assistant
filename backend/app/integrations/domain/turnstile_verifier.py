"""`TurnstileVerifier`: puerto para la verificación anti-bot de Cloudflare
Turnstile en el alta pública de clínica (Fase 12, hito 12.4 ampliado — ver
docs/fase-12-rfc.md §6, decisión del 2026-09-18).

Mismo patrón `Protocol` + factory que `EmailSender`/`TranscriptionProvider`
— la implementación real se resuelve por configuración
(`TURNSTILE_PROVIDER`) en `app/integrations/factory.py::build_turnstile_verifier`.
`TURNSTILE_PROVIDER=mock` (por defecto, `MockTurnstileVerifier`) nunca
llama a un servicio externo.
"""

from __future__ import annotations

from typing import Protocol


class TurnstileVerifier(Protocol):
    async def verify(self, token: str, *, remote_ip: str | None) -> bool:
        """`token`: el valor `cf-turnstile-response` devuelto por el widget
        en el frontend. `remote_ip`: la IP real del cliente si se conoce
        (mejora la puntuación de Cloudflare, nunca obligatoria — ver
        app/core/rate_limit.py::client_ip_key para su extracción). Devuelve
        `True` si el desafío es válido; nunca lanza por un token inválido o
        caducado, solo por un fallo de configuración/transporte (ver
        implementaciones concretas)."""
        ...
