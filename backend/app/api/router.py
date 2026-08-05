"""Agregador de la API versionada /api/v1."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.schemas import CurrentUserResponse
from app.core.config import Settings, get_settings
from app.core.current_user import CurrentUser
from app.core.deps import get_current_user
from app.patients.api.router import router as patients_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(patients_router)


@v1_router.get("/me", response_model=CurrentUserResponse, tags=["dev-tools"])
async def get_me(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse.model_validate(current_user)


def register_dev_tools(router: APIRouter, settings: Settings | None = None) -> None:
    """Registra rutas exclusivas de desarrollo. No-op en producción."""
    settings = settings or get_settings()
    if settings.is_production:
        return
    from app.api.dev_tools import router as dev_tools_router

    router.include_router(dev_tools_router)


register_dev_tools(v1_router)
