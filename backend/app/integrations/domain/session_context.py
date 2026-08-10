"""Contexto mínimo compartido por los generators del AI Pipeline.

Value object deliberadamente pequeño: en esta fase ningún `Mock*` necesita
más que el identificador de la sesión, pero mantenerlo como su propio tipo
(en vez de pasar un `uuid.UUID` suelto) deja sitio para añadir contexto
adicional en el futuro (p. ej. idioma preferido) sin cambiar la firma de
ninguna interfaz de proveedor.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class SessionContext:
    clinical_session_id: uuid.UUID
