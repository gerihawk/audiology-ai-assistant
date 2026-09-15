"""Rate limiting (Fase 10.5).

`Limiter` de slowapi con almacenamiento EN MEMORIA del proceso (backend por
defecto, sin Redis) — aceptado explícitamente para el despliegue actual de
una única instancia en Railway. Dos consecuencias directas de esa elección:
el contador se resetea en cada redeploy, y deja de ser un límite correcto
en cuanto exista más de una réplica del backend corriendo a la vez (cada
proceso llevaría su propio contador). Si Railway pasa a multi-réplica,
esto necesita moverse a un backend compartido (p. ej. Redis) — ver
https://slowapi.readthedocs.io/en/latest/#configuring-a-storage-backend.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _client_ip_key(request: Request) -> str:
    """Clave de rate limit por IP real del cliente, no del socket TCP.

    Hallazgo verificado en production (Railway): `get_remote_address`
    (usa `request.client.host`, la IP del socket TCP directo) devuelve la
    IP del propio proxy de Railway, no la del cliente externo, y esa IP
    del proxy varía entre peticiones — cada petición contaba como una "IP"
    distinta y el límite de login (5/minute) nunca se disparaba (6
    peticiones seguidas seguían dando 401 en vez de 429 en la sexta).

    `X-Forwarded-For` sí lleva la IP real del cliente en su primer valor
    (el más a la izquierda) cuando la pone Railway. Asunción de confianza
    que esto implica, y que debe seguir siendo cierta para que este valor
    sea fiable: TODO el tráfico público llega a través del proxy de
    Railway (nunca directo a la app), y Railway sobrescribe/sanea
    `X-Forwarded-For` en vez de reenviar sin más el valor que ya traiga la
    petición entrante — si cualquiera de las dos deja de cumplirse, un
    cliente podría falsificar esta cabecera para evadir el límite.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    # Sin proxy delante (desarrollo local, tests): mismo comportamiento que
    # antes.
    return get_remote_address(request)


limiter = Limiter(key_func=_client_ip_key, default_limits=["120/minute"])
