"""Excepciones de dominio, independientes de FastAPI.

Se traducen a respuestas HTTP en app.core.errors. Ningún módulo de
dominio o servicio debe lanzar HTTPException directamente.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base para todos los errores de dominio."""


class NotFoundError(DomainError):
    """El recurso no existe o no pertenece a la clínica del usuario actual.

    Deliberadamente el mismo error en ambos casos: nunca se distingue
    "no existe" de "pertenece a otra clínica" para no filtrar la
    existencia de datos ajenos a la clínica del usuario.
    """


class ConflictError(DomainError):
    """El estado actual del recurso impide la operación (p. ej. código duplicado)."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class ForbiddenError(DomainError):
    """El usuario actual no tiene permiso para realizar la acción."""


class UnauthenticatedError(DomainError):
    """No se pudo resolver un usuario actual válido."""
