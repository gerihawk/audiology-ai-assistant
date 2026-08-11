"""Límite duro de coste LLM por sesión (hito 6.1, docs/fase-6-rfc.md §6.3)
cableado en `AIPipelineService` — con `llm_cost_limit_enforced=False`
(valor por defecto) el comportamiento es idéntico al resto de la suite,
igual que el consentimiento del hito 6.0 (ver test_ai_pipeline_consent.py,
mismo patrón de `monkeypatch` sobre `get_settings`). Este archivo solo
cubre el flag activado."""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_pipeline import service as ai_pipeline_service_module
from app.ai_pipeline.domain.entities import AIArtifactType, AIGenerationRunStatus
from app.ai_pipeline.service import AIPipelineService
from app.core.config import get_settings
from app.patients.domain.entities import Patient
from tests.factories import ClinicWithUsers, current_user_from, dev_headers


class _FixedCostEstimator:
    """Coste fijo por llamada, sin depender de tokens — MockCostEstimator
    real (coste 0) nunca podría disparar el límite, así que estos tests
    inyectan este doble en su lugar (encargo Fase 6.1, punto 9: "no
    considerar MockCostEstimator como coste real")."""

    def __init__(self, cost_per_call: Decimal) -> None:
        self._cost_per_call = cost_per_call

    def estimate(self, *, provider, model, input_tokens, output_tokens) -> Decimal:
        return self._cost_per_call


def _enforce_cost_limit(monkeypatch, *, limit_usd: Decimal) -> None:
    settings = get_settings().model_copy(
        update={"llm_cost_limit_enforced": True, "max_llm_cost_per_session_usd": limit_usd}
    )
    monkeypatch.setattr(ai_pipeline_service_module, "get_settings", lambda: settings)


async def _create_session(
    api_client: AsyncClient, headers: dict[str, str], patient_id: str, professional_id: str
) -> dict:
    response = await api_client.post(
        "/api/v1/clinical-sessions",
        json={
            "patient_id": patient_id,
            "professional_id": professional_id,
            "session_type": "initial_assessment",
            "status": "completed",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _outcome_for(outcomes, artifact_type: AIArtifactType):
    return next(o for o in outcomes if o.artifact_type == artifact_type)


async def test_coste_potencial_excede_el_limite_bloquea_el_primer_step(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    _enforce_cost_limit(monkeypatch, limit_usd=Decimal("0.01"))
    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )

    current_user = current_user_from(clinic_with_users.admin)
    service = AIPipelineService(db_session, cost_estimator=_FixedCostEstimator(Decimal("1.00")))

    result = await service.run_pipeline(current_user, uuid.UUID(session["id"]), "req-cost-1")

    transcript_outcome = _outcome_for(result.outcomes, AIArtifactType.TRANSCRIPT)
    assert transcript_outcome.status == AIGenerationRunStatus.FAILED
    assert transcript_outcome.failure_reason == "cost_limit_exceeded"
    # El resto de steps dependen (en cascada) de transcript -> se saltan,
    # nunca se invoca al proveedor para ellos tampoco.
    summary_outcome = _outcome_for(result.outcomes, AIArtifactType.SUMMARY)
    assert summary_outcome.status is None
    assert result.pipeline_run.status.value == "failed"


async def test_coste_acumulado_de_una_ejecucion_previa_bloquea_la_siguiente(
    api_client: AsyncClient,
    clinic_with_users: ClinicWithUsers,
    patient: Patient,
    db_session: AsyncSession,
    monkeypatch,
):
    """El límite es por SESIÓN, no por ejecución — ver docs/fase-6-rfc.md
    §6.3. Cinco steps a 15 USD cada uno (75 USD) caben en un límite de 100
    en la primera ejecución; en la segunda, el coste ya acumulado deja
    presupuesto solo para el primer step."""
    _enforce_cost_limit(monkeypatch, limit_usd=Decimal("100"))
    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )

    current_user = current_user_from(clinic_with_users.admin)
    session_id = uuid.UUID(session["id"])
    cost_estimator = _FixedCostEstimator(Decimal("15"))

    first_run = await AIPipelineService(db_session, cost_estimator=cost_estimator).run_pipeline(
        current_user, session_id, "req-cost-a"
    )
    assert all(
        o.status == AIGenerationRunStatus.COMPLETED for o in first_run.outcomes
    ), first_run.outcomes

    second_run = await AIPipelineService(db_session, cost_estimator=cost_estimator).run_pipeline(
        current_user, session_id, "req-cost-b"
    )

    transcript_outcome = _outcome_for(second_run.outcomes, AIArtifactType.TRANSCRIPT)
    assert transcript_outcome.status == AIGenerationRunStatus.COMPLETED  # 75 + 15 = 90 <= 100

    summary_outcome = _outcome_for(second_run.outcomes, AIArtifactType.SUMMARY)
    assert summary_outcome.status == AIGenerationRunStatus.FAILED  # 90 + 15 = 105 > 100
    assert summary_outcome.failure_reason == "cost_limit_exceeded"


async def test_limite_desactivado_por_defecto_no_cambia_el_comportamiento(
    api_client: AsyncClient, clinic_with_users: ClinicWithUsers, patient: Patient
):
    headers = dev_headers(clinic_with_users.admin)
    session = await _create_session(
        api_client, headers, str(patient.id), str(clinic_with_users.audiologist.id)
    )
    response = await api_client.post(
        f"/api/v1/clinical-sessions/{session['id']}/run-mock-pipeline", headers=headers
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "completed"
