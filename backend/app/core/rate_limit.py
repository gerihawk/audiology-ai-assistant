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

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])
