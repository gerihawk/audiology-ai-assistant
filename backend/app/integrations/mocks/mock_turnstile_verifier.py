"""MockTurnstileVerifier: TURNSTILE_PROVIDER=mock (por defecto) — sin
verificación real.

Mismo espíritu que `ConsoleEmailSender`/`MockTranscriptionProvider`: nunca
contacta a Cloudflare, siempre aprueba. Necesario para desarrollo local y
para toda la suite de tests (que no tienen ni necesitan un site key/secret
key real de Turnstile) — nunca usar en production (decisión operativa de
Gerard, igual que el resto de proveedores "mock", sin guardarraíl propio en
`_validate_production_safety`)."""

from __future__ import annotations

import logging

logger = logging.getLogger("app.integrations.turnstile.mock")


class MockTurnstileVerifier:
    async def verify(self, token: str, *, remote_ip: str | None) -> bool:
        logger.info(
            "Verificación Turnstile simulada (TURNSTILE_PROVIDER=mock) — "
            "siempre aprobada, nunca contacta a Cloudflare",
            extra={"context": {"remote_ip": remote_ip}},
        )
        return True
