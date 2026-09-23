"""Orquestación de la auditoría LLM no bloqueante (Paso 2 del cierre del
hallazgo bloqueante del red team, docs/security/red-team-app-2026-09-22.md
§A1).

Se dispara como `BackgroundTasks` de FastAPI desde
`app/ai_pipeline/api/router.py::run_pipeline` — SOLO ese endpoint, nunca
`run_mock_pipeline` (que es estructuralmente incapaz de gastar dinero o
contactar a un proveedor real, sin importar `Settings`; añadir esta
llamada ahí rompería esa garantía). `BackgroundTasks` ejecuta después de
que la respuesta ya se envió al cliente — nunca en el camino crítico.

Abre su PROPIA sesión de base de datos (`get_session_factory()`): la
sesión de la petición que disparó el pipeline pertenece al ciclo de vida
de esa petición y no debe reutilizarse aquí.

Cualquier excepción del proveedor (red, timeout, JSON inválido, forma de
respuesta inesperada) se captura y se registra como auditoría no
concluyente — nunca se propaga, nunca falla nada del pipeline que ya
completó y ya se le devolvió al usuario."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline.domain.safety_audit import (
    PROMPT_VERSION,
    RESPONSE_JSON_SCHEMA,
    build_safety_audit_prompt,
    parse_safety_audit_response,
)
from app.ai_pipeline.infrastructure.repository import SqlAlchemyAISafetyAuditFlagRepository
from app.core.config import Settings, get_settings
from app.core.db import get_session_factory
from app.integrations.domain.language_model_provider import LanguageModelProvider
from app.integrations.factory import build_safety_audit_provider

logger = logging.getLogger("app.ai_pipeline")


async def run_safety_audit(
    clinic_id: uuid.UUID,
    artifact_versions: dict[str, tuple[uuid.UUID, str]],
    *,
    settings: Settings | None = None,
    provider: LanguageModelProvider | None = None,
    repository: SqlAlchemyAISafetyAuditFlagRepository | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> None:
    """`artifact_versions` es `{artifact_type: (ai_artifact_version_id,
    contenido_como_texto)}` — el llamador ya lo filtró a solo los
    artefactos que completaron con éxito y ya pasaron `validate_safety`
    (Paso 1). No hace nada — ni siquiera construye el proveedor mock — si
    `LLM_PROVIDER_SAFETY_AUDIT` está en `"off"` (valor por defecto en todos
    los entornos) o si no hay ningún artefacto que auditar.

    `settings`/`provider`/`repository`/`session_factory` son inyectables
    exclusivamente para tests (mismo criterio del resto del pipeline, ver
    `AIPipelineService.__init__`) — en producción se resuelven todos por
    configuración/factory reales."""
    if not artifact_versions:
        return
    settings = settings or get_settings()
    if provider is None:
        provider = build_safety_audit_provider(settings)
    if provider is None:
        return

    contents = {artifact_type: text for artifact_type, (_, text) in artifact_versions.items()}
    model = settings.llm_model_safety_audit

    try:
        prompt = build_safety_audit_prompt(contents)
        response = await provider.complete(
            prompt, model=model, response_json_schema=RESPONSE_JSON_SCHEMA
        )
        verdict = parse_safety_audit_response(response.text)
    # Cualquier fallo del proveedor (red, timeout, JSON inválido, forma de
    # respuesta inesperada) es "no concluyente" — nunca se propaga, ver
    # docstring del módulo.
    except Exception:  # noqa: BLE001
        logger.warning(
            "Auditoría de seguridad no concluyente: excepción/timeout/fallo de parseo "
            "del proveedor.",
            extra={"clinic_id": str(clinic_id), "artifact_types": sorted(contents)},
            exc_info=True,
        )
        return

    if not verdict.flagged:
        return

    # Si el modelo señaló un `field` que coincide exactamente con uno de
    # los artifact_type auditados, la fila se asocia solo a ese artefacto.
    # Si no (campo ambiguo, general o `null`), se asocia a TODOS los
    # artefactos auditados en esta sesión — preferible a perder la señal
    # por no saber a cuál de ellos atribuirla.
    matched_type = verdict.field if verdict.field in artifact_versions else None
    targets = (
        [artifact_versions[matched_type]]
        if matched_type is not None
        else list(artifact_versions.values())
    )

    repository = repository or SqlAlchemyAISafetyAuditFlagRepository()
    open_session = session_factory or get_session_factory()
    async with open_session() as session:
        for ai_artifact_version_id, _ in targets:
            await repository.add(
                session,
                ai_artifact_version_id=ai_artifact_version_id,
                clinic_id=clinic_id,
                llm_flagged=True,
                # Recortado a 500 (límite de columna) — nunca el texto
                # marcado completo, solo el motivo que dio el modelo.
                llm_reasoning=verdict.reasoning[:500],
                model_used=model or provider.__class__.__name__,
                prompt_version=PROMPT_VERSION,
            )
        await session.commit()
