"""Tests de dominio puro de las primitivas de actualización longitudinal
de ANAMNESIS — Hito 6.5.1 (RFC técnico de 6.5, decisiones cerradas
§1-§12). Sin base de datos, sin proveedor, sin interpretación de lenguaje
natural: todos los `AnamnesisFieldUpdate` de este módulo son propuestas
YA construidas a mano (equivalente a lo que un generador de 6.5.2
produciría), nunca inferidas de un transcript por regla alguna."""

from __future__ import annotations

import copy

import pytest

from app.ai_pipeline.domain.anamnesis_update import (
    AnamnesisFieldUpdate,
    AnamnesisUpdateReason,
    InvalidAnamnesisUpdateError,
    materialize_anamnesis,
    validate_update_batch,
    verify_update_grounding,
)
from app.ai_pipeline.domain.entities import AIArtifactType
from app.ai_pipeline.domain.schemas import validate_content_schema
from app.integrations.domain.anamnesis_generator import ANAMNESIS_FIELDS, AnamnesisFieldStatus
from tests.clinical_fixtures import LONGITUDINAL_ONLY_PHRASE

_CURRENT_TRANSCRIPT = (
    "AUDIOPROTESISTA: ¿Ha notado pitidos en los oídos?\n"
    "PACIENTE: Sí, un pitido leve en el oído derecho desde hace una semana.\n"
    "AUDIOPROTESISTA: Entendido, lo anoto."
)
_CURRENT_TRANSCRIPT_EXCERPT = "un pitido leve en el oído derecho desde hace una semana"


def _baseline() -> dict:
    return {
        name: {
            "value": "",
            "status": AnamnesisFieldStatus.NO_PREGUNTADO.value,
            "source_excerpt": None,
        }
        for name in ANAMNESIS_FIELDS
    }


def _baseline_with(
    field_name: str, *, value: str, status: AnamnesisFieldStatus, source_excerpt: str | None
) -> dict:
    content = _baseline()
    content[field_name] = {"value": value, "status": status.value, "source_excerpt": source_excerpt}
    return content


def _update(
    field_name: str = "tinnitus",
    *,
    previous_value: str = "",
    previous_status: AnamnesisFieldStatus = AnamnesisFieldStatus.NO_PREGUNTADO,
    proposed_value: str = "Pitido leve en oído derecho.",
    proposed_status: AnamnesisFieldStatus = AnamnesisFieldStatus.INFORMADO,
    source_excerpt: str = _CURRENT_TRANSCRIPT_EXCERPT,
    reason: AnamnesisUpdateReason = AnamnesisUpdateReason.FILLS_GAP,
) -> AnamnesisFieldUpdate:
    return AnamnesisFieldUpdate(
        field_name=field_name,
        previous_value=previous_value,
        previous_status=previous_status,
        proposed_value=proposed_value,
        proposed_status=proposed_status,
        source_excerpt=source_excerpt,
        reason=reason,
    )


# ============================================================
# B. fills_gap — transiciones válidas
# ============================================================


class TestFillsGapValidTransitions:
    def test_no_preguntado_to_informado_is_valid(self):
        validate_update_batch(
            [
                _update(
                    previous_status=AnamnesisFieldStatus.NO_PREGUNTADO,
                    proposed_status=AnamnesisFieldStatus.INFORMADO,
                    reason=AnamnesisUpdateReason.FILLS_GAP,
                )
            ]
        )  # no debe lanzar

    def test_no_determinado_to_informado_is_valid(self):
        validate_update_batch(
            [
                _update(
                    previous_status=AnamnesisFieldStatus.NO_DETERMINADO,
                    proposed_status=AnamnesisFieldStatus.INFORMADO,
                    reason=AnamnesisUpdateReason.FILLS_GAP,
                )
            ]
        )

    def test_no_preguntado_to_negado_explicitamente_is_valid(self):
        validate_update_batch(
            [
                _update(
                    previous_status=AnamnesisFieldStatus.NO_PREGUNTADO,
                    proposed_status=AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE,
                    proposed_value="Niega pitidos.",
                    reason=AnamnesisUpdateReason.FILLS_GAP,
                )
            ]
        )


# ============================================================
# C. explicit_correction — transiciones válidas
# ============================================================


class TestExplicitCorrectionValidTransitions:
    def test_informado_to_negado_explicitamente_is_valid(self):
        validate_update_batch(
            [
                _update(
                    previous_value="Pitido leve.",
                    previous_status=AnamnesisFieldStatus.INFORMADO,
                    proposed_value="Niega pitidos (corrección).",
                    proposed_status=AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE,
                    reason=AnamnesisUpdateReason.EXPLICIT_CORRECTION,
                )
            ]
        )

    def test_negado_explicitamente_to_informado_is_valid(self):
        validate_update_batch(
            [
                _update(
                    previous_value="Niega pitidos.",
                    previous_status=AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE,
                    proposed_value="Sí nota pitidos (corrección).",
                    proposed_status=AnamnesisFieldStatus.INFORMADO,
                    reason=AnamnesisUpdateReason.EXPLICIT_CORRECTION,
                )
            ]
        )

    def test_informado_to_informado_with_different_value_is_valid(self):
        validate_update_batch(
            [
                _update(
                    previous_value="Pitido leve en oído izquierdo.",
                    previous_status=AnamnesisFieldStatus.INFORMADO,
                    proposed_value="Pitido leve en oído derecho (corrección).",
                    proposed_status=AnamnesisFieldStatus.INFORMADO,
                    reason=AnamnesisUpdateReason.EXPLICIT_CORRECTION,
                )
            ]
        )


# ============================================================
# D. combinaciones reason/previous_status inválidas
# ============================================================


class TestInvalidReasonCombinations:
    def test_informado_with_fills_gap_is_invalid(self):
        with pytest.raises(InvalidAnamnesisUpdateError):
            validate_update_batch(
                [
                    _update(
                        previous_value="Pitido leve.",
                        previous_status=AnamnesisFieldStatus.INFORMADO,
                        proposed_value="Pitido intenso.",
                        proposed_status=AnamnesisFieldStatus.INFORMADO,
                        reason=AnamnesisUpdateReason.FILLS_GAP,
                    )
                ]
            )

    def test_negado_explicitamente_with_fills_gap_is_invalid(self):
        with pytest.raises(InvalidAnamnesisUpdateError):
            validate_update_batch(
                [
                    _update(
                        previous_value="Niega pitidos.",
                        previous_status=AnamnesisFieldStatus.NEGADO_EXPLICITAMENTE,
                        proposed_value="Sí nota pitidos.",
                        proposed_status=AnamnesisFieldStatus.INFORMADO,
                        reason=AnamnesisUpdateReason.FILLS_GAP,
                    )
                ]
            )

    def test_no_preguntado_with_explicit_correction_is_invalid(self):
        with pytest.raises(InvalidAnamnesisUpdateError):
            validate_update_batch(
                [
                    _update(
                        previous_status=AnamnesisFieldStatus.NO_PREGUNTADO,
                        proposed_status=AnamnesisFieldStatus.INFORMADO,
                        reason=AnamnesisUpdateReason.EXPLICIT_CORRECTION,
                    )
                ]
            )

    def test_no_determinado_with_explicit_correction_is_invalid(self):
        with pytest.raises(InvalidAnamnesisUpdateError):
            validate_update_batch(
                [
                    _update(
                        previous_status=AnamnesisFieldStatus.NO_DETERMINADO,
                        proposed_status=AnamnesisFieldStatus.INFORMADO,
                        reason=AnamnesisUpdateReason.EXPLICIT_CORRECTION,
                    )
                ]
            )


# ============================================================
# E. proposed_status de laguna — inválido
# ============================================================


class TestProposedStatusNeverAGap:
    def test_proposed_status_no_determinado_is_invalid(self):
        with pytest.raises(InvalidAnamnesisUpdateError):
            validate_update_batch(
                [
                    _update(
                        previous_status=AnamnesisFieldStatus.NO_PREGUNTADO,
                        proposed_status=AnamnesisFieldStatus.NO_DETERMINADO,
                        reason=AnamnesisUpdateReason.FILLS_GAP,
                    )
                ]
            )

    def test_proposed_status_no_preguntado_is_invalid(self):
        with pytest.raises(InvalidAnamnesisUpdateError):
            validate_update_batch(
                [
                    _update(
                        previous_status=AnamnesisFieldStatus.NO_DETERMINADO,
                        proposed_status=AnamnesisFieldStatus.NO_PREGUNTADO,
                        reason=AnamnesisUpdateReason.FILLS_GAP,
                    )
                ]
            )


# ============================================================
# F. no-op — inválido
# ============================================================


class TestNoOpIsInvalid:
    def test_identical_value_and_status_is_invalid(self):
        with pytest.raises(InvalidAnamnesisUpdateError):
            validate_update_batch(
                [
                    _update(
                        previous_value="Pitido leve.",
                        previous_status=AnamnesisFieldStatus.INFORMADO,
                        proposed_value="Pitido leve.",
                        proposed_status=AnamnesisFieldStatus.INFORMADO,
                        reason=AnamnesisUpdateReason.EXPLICIT_CORRECTION,
                    )
                ]
            )


# ============================================================
# G. campo desconocido — inválido
# ============================================================


class TestUnknownFieldIsInvalid:
    def test_unrecognized_field_name_is_invalid(self):
        with pytest.raises(InvalidAnamnesisUpdateError):
            validate_update_batch([_update(field_name="campo_que_no_existe")])


# ============================================================
# H. campo duplicado — inválido
# ============================================================


class TestDuplicateFieldIsInvalid:
    def test_two_updates_for_same_field_is_invalid(self):
        first = _update(
            field_name="tinnitus",
            previous_status=AnamnesisFieldStatus.NO_PREGUNTADO,
            proposed_status=AnamnesisFieldStatus.INFORMADO,
            reason=AnamnesisUpdateReason.FILLS_GAP,
        )
        second = _update(
            field_name="tinnitus",
            previous_value="Pitido leve.",
            previous_status=AnamnesisFieldStatus.INFORMADO,
            proposed_value="Pitido intenso (corrección).",
            proposed_status=AnamnesisFieldStatus.INFORMADO,
            reason=AnamnesisUpdateReason.EXPLICIT_CORRECTION,
        )
        with pytest.raises(InvalidAnamnesisUpdateError):
            validate_update_batch([first, second])


# ============================================================
# I/J/K. Grounding acotado
# ============================================================


class TestBoundedGrounding:
    def test_excerpt_present_in_current_transcript_grounds(self):
        update = _update(source_excerpt=_CURRENT_TRANSCRIPT_EXCERPT)
        result = verify_update_grounding([update], _CURRENT_TRANSCRIPT)
        assert result.ok is True
        assert result.failure_reason is None
        # Coincidencia literal: verify_excerpt() también informa offsets en
        # el texto original (ver grounding.py) — mismo formato ya usado por
        # _build_source_map para el resto de artefactos.
        assert result.source_map.keys() == {"tinnitus"}
        assert result.source_map["tinnitus"]["field"] == "tinnitus"
        assert result.source_map["tinnitus"]["excerpt"] == _CURRENT_TRANSCRIPT_EXCERPT
        assert result.source_map["tinnitus"]["original_start"] == _CURRENT_TRANSCRIPT.index(
            _CURRENT_TRANSCRIPT_EXCERPT
        )

    def test_excerpt_present_only_in_longitudinal_context_fails_grounding(self):
        """El excerpt existe (es texto real), pero solo en el contexto
        longitudinal — nunca en el transcript actual. Debe fallar, nunca
        aceptarse como evidencia de la sesión actual (RFC técnico §7/§11)."""
        update = _update(source_excerpt=LONGITUDINAL_ONLY_PHRASE)
        result = verify_update_grounding([update], _CURRENT_TRANSCRIPT)
        assert result.ok is False
        assert result.failure_reason is not None
        assert result.ungrounded_fields == ("tinnitus",)
        assert result.source_map is None

    def test_fabricated_excerpt_fails_grounding(self):
        fabricated = "una frase que no aparece en ningún transcript de este test"
        update = _update(source_excerpt=fabricated)
        result = verify_update_grounding([update], _CURRENT_TRANSCRIPT)
        assert result.ok is False
        assert result.source_map is None

    def test_grounding_never_receives_previous_anamnesis_as_reference_text(self):
        """Defensa explícita: aunque alguien pasara por error el contenido
        de la anamnesis previa como `current_transcript`, la función no
        tiene ningún parámetro adicional para "contexto longitudinal" —
        solo compara contra lo que se le pasa como transcript actual."""
        update = _update(source_excerpt=LONGITUDINAL_ONLY_PHRASE)
        # Si alguien confundiera el contexto previo con el transcript
        # actual, el grounding "pasaría" — por eso el propio step (6.5.2+)
        # nunca debe construir `current_transcript` a partir de la
        # anamnesis previa. Aquí solo demostramos que la primitiva es
        # ciega a esa distinción: la responsabilidad de no mezclar los dos
        # canales es del llamador, documentado en el docstring del módulo.
        result = verify_update_grounding([update], LONGITUDINAL_ONLY_PHRASE)
        assert result.ok is True  # confirma que la primitiva es genérica, sin lista negra


# ============================================================
# L. Materialización
# ============================================================


class TestMaterialization:
    def test_only_changed_fields_are_altered(self):
        baseline = _baseline()
        update = _update(
            field_name="tinnitus",
            previous_status=AnamnesisFieldStatus.NO_PREGUNTADO,
            proposed_value="Pitido leve.",
            proposed_status=AnamnesisFieldStatus.INFORMADO,
            reason=AnamnesisUpdateReason.FILLS_GAP,
        )
        result = materialize_anamnesis(baseline, [update])

        assert result["tinnitus"] == {
            "value": "Pitido leve.",
            "status": "informado",
            "source_excerpt": _CURRENT_TRANSCRIPT_EXCERPT,
        }
        for field_name in ANAMNESIS_FIELDS:
            if field_name == "tinnitus":
                continue
            assert result[field_name] == baseline[field_name]

    def test_baseline_is_never_mutated(self):
        baseline = _baseline()
        baseline_snapshot = copy.deepcopy(baseline)
        update = _update(
            field_name="tinnitus",
            previous_status=AnamnesisFieldStatus.NO_PREGUNTADO,
            proposed_status=AnamnesisFieldStatus.INFORMADO,
            reason=AnamnesisUpdateReason.FILLS_GAP,
        )
        materialize_anamnesis(baseline, [update])
        assert baseline == baseline_snapshot

    def test_result_passes_anamnesis_schema(self):
        baseline = _baseline()
        update = _update(
            field_name="tinnitus",
            previous_status=AnamnesisFieldStatus.NO_PREGUNTADO,
            proposed_status=AnamnesisFieldStatus.INFORMADO,
            reason=AnamnesisUpdateReason.FILLS_GAP,
        )
        result = materialize_anamnesis(baseline, [update])
        schema_result = validate_content_schema(AIArtifactType.ANAMNESIS, result)
        assert schema_result.valid, schema_result.errors

    def test_rejects_update_whose_previous_state_does_not_match_real_baseline(self):
        """Comprobación de consistencia añadida en 6.5.1 (no pedida
        literalmente, pero necesaria para la garantía de seguridad
        clínica del hito): un update que declara un `previous_status`
        distinto del real en el baseline se rechaza, en vez de aplicarse
        sobre una premisa falsa."""
        baseline = _baseline_with(
            "tinnitus",
            value="Pitido leve.",
            status=AnamnesisFieldStatus.INFORMADO,
            source_excerpt="excerpt histórico",
        )
        update = _update(
            field_name="tinnitus",
            previous_value="",  # no coincide con el baseline real ("Pitido leve.")
            previous_status=AnamnesisFieldStatus.NO_PREGUNTADO,
            proposed_status=AnamnesisFieldStatus.INFORMADO,
            reason=AnamnesisUpdateReason.FILLS_GAP,
        )
        with pytest.raises(InvalidAnamnesisUpdateError):
            materialize_anamnesis(baseline, [update])


# ============================================================
# M. source_map — solo campos modificados
# ============================================================


class TestSourceMapOnlyContainsModifiedFields:
    def test_source_map_excludes_carried_forward_fields(self):
        update = _update(field_name="tinnitus", source_excerpt=_CURRENT_TRANSCRIPT_EXCERPT)
        result = verify_update_grounding([update], _CURRENT_TRANSCRIPT)
        assert set(result.source_map.keys()) == {"tinnitus"}

    def test_source_map_with_two_changed_fields_contains_only_those_two(self):
        second_transcript = _CURRENT_TRANSCRIPT + "\nPACIENTE: También me duele el oído."
        updates = [
            _update(field_name="tinnitus", source_excerpt=_CURRENT_TRANSCRIPT_EXCERPT),
            _update(
                field_name="otalgia",
                proposed_value="Dolor de oído.",
                source_excerpt="me duele el oído",
            ),
        ]
        result = verify_update_grounding(updates, second_transcript)
        assert result.ok is True
        assert set(result.source_map.keys()) == {"tinnitus", "otalgia"}


# ============================================================
# N. Lista vacía
# ============================================================


class TestEmptyUpdateList:
    def test_validate_empty_batch_does_not_raise(self):
        validate_update_batch([])  # sin cambios propuestos es un resultado válido

    def test_materialize_with_no_updates_returns_baseline_copy(self):
        baseline = _baseline()
        result = materialize_anamnesis(baseline, [])
        assert result == baseline
        assert result is not baseline  # copia, nunca el mismo objeto

    def test_grounding_of_empty_batch_is_ok_with_no_source_map(self):
        result = verify_update_grounding([], _CURRENT_TRANSCRIPT)
        assert result.ok is True
        assert result.source_map is None
        assert result.failure_reason is None
