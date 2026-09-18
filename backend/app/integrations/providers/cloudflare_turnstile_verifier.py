"""CloudflareTurnstileVerifier: TURNSTILE_PROVIDER=cloudflare (Fase 12,
hito 12.4 ampliado, decisión del 2026-09-18 — ver docs/fase-12-rfc.md §6).

Usa exclusivamente la API REST oficial de Turnstile (`POST
/turnstile/v0/siteverify`) vía `httpx` — sin SDK de terceros, mismo
criterio que `BrevoEmailSender`/`DeepgramTranscriptionProvider`. La secret
key nunca se registra en logs ni se incluye en ninguna excepción — solo
viaja en el cuerpo de la petición a Cloudflare (ver CLAUDE.md, Secret
handling).

Deliberadamente permisivo ante fallos de transporte/5xx de Cloudflare: un
timeout o una caída del servicio de Cloudflare no debe bloquear el alta de
clínicas legítimas (Turnstile es una capa de defensa entre varias — ver
también el bloqueo de dominios desechables y el rate limiting existente,
docs/fase-12-rfc.md §6), así que `verify()` devuelve `False` (rechaza ese
intento concreto, el usuario puede reintentar) en vez de lanzar una excepción
de 500 que tumbe el endpoint entero. Solo un secret key ausente/vacío en
config es un error de arranque (`ValueError` en `__init__`, igual que
`BrevoEmailSender`)."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("app.integrations.turnstile.cloudflare")

_SITEVERIFY_PATH = "/turnstile/v0/siteverify"


class CloudflareTurnstileVerifier:
    def __init__(
        self,
        *,
        secret_key: str | None,
        base_url: str = "https://challenges.cloudflare.com",
        timeout_seconds: float = 10.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not secret_key:
            raise ValueError(
                "TURNSTILE_SECRET_KEY es obligatoria para usar CloudflareTurnstileVerifier "
                "(TURNSTILE_PROVIDER=cloudflare)."
            )
        self._secret_key = secret_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._injected_client = http_client

    async def verify(self, token: str, *, remote_ip: str | None) -> bool:
        if not token:
            return False
        client = self._injected_client or httpx.AsyncClient(base_url=self._base_url)
        owns_client = self._injected_client is None
        payload = {"secret": self._secret_key, "response": token}
        if remote_ip:
            payload["remoteip"] = remote_ip
        try:
            response = await client.post(
                _SITEVERIFY_PATH,
                data=payload,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError):
            # Timeout, 5xx de Cloudflare, o JSON inválido: no es culpa del
            # visitante — ver docstring del módulo.
            logger.warning("Fallo de transporte al verificar Turnstile", exc_info=True)
            return False
        finally:
            if owns_client:
                await client.aclose()
        return bool(body.get("success", False))
