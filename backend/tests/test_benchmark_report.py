"""Tests de benchmark/report.py: serialización del esquema extendido del
resultado del benchmark (Fase 5.1) — ver docs/transcription-benchmark.md
§Benchmark result schema."""

from __future__ import annotations

import json

from app.integrations.domain.transcription_provider import TranscriptionResult, TranscriptionSegment
from benchmark.dataset_metadata import DatasetMetadata, LateralityCase, NegationCase
from benchmark.reference import Reference, ReferenceSegment, ReferenceSpeaker
from benchmark.report import build_report, write_report
from benchmark.runner import BenchmarkOutcome

_REFERENCE = Reference(
    language="es",
    speakers=[
        ReferenceSpeaker(id="audiologist", label="Audioprotesista"),
        ReferenceSpeaker(id="patient", label="Paciente"),
    ],
    segments=[
        ReferenceSegment(speaker="audiologist", text="¿Tiene acúfenos?"),
        ReferenceSegment(speaker="patient", text="Sí, tengo acúfenos y no tengo vértigo."),
    ],
)

_METADATA = DatasetMetadata(
    id="consulta_ficticia_01",
    description="Caso de prueba",
    language="es",
    number_of_speakers=2,
    environment="quiet_clinic",
    noise_level=None,
    duration_expected_seconds=None,
    critical_terms=["acúfenos"],
    negation_cases=[
        NegationCase(
            concept="vertigo", expected="negated", patterns={"negated": ["no tengo vértigo"]}
        )
    ],
    laterality_cases=[
        LateralityCase(concept="tinnitus", laterality="left", patterns={"left": ["izquierdo"]})
    ],
    notes=None,
)


def _success_outcome(
    text: str = "¿Tiene acúfenos? Sí, tengo acúfenos y no tengo vértigo.",
) -> BenchmarkOutcome:
    return BenchmarkOutcome(
        provider="mock",
        audio_id="consulta_ficticia_01",
        ran_at="2026-01-01T00:00:00+00:00",
        response_time_ms=42,
        result=TranscriptionResult(
            text=text,
            language="es",
            confidence=70,
            duration_ms=8000,
            segments=[
                TranscriptionSegment(speaker="A", start_ms=0, end_ms=4000, text="¿Tiene acúfenos?"),
                TranscriptionSegment(
                    speaker="B",
                    start_ms=4000,
                    end_ms=8000,
                    text="Sí, tengo acúfenos y no tengo vértigo.",
                ),
            ],
            model_name="mock-v1",
            provider_metadata=None,
        ),
        error=None,
    )


def _failure_outcome() -> BenchmarkOutcome:
    return BenchmarkOutcome(
        provider="deepgram",
        audio_id="consulta_ficticia_01",
        ran_at="2026-01-01T00:00:00+00:00",
        response_time_ms=5,
        result=None,
        error="'deepgram' no es un proveedor de transcripción reconocido.",
    )


def _build(outcome, *, reference=None, metadata=None):
    return build_report(
        outcome,
        estimated_cost_usd="0",
        estimated_cost_source="mock",
        pricing_version=None,
        pricing_effective_date=None,
        reference=reference,
        metadata=metadata,
    )


def test_esquema_basico_sin_reference_ni_metadata():
    report = _build(_success_outcome())

    assert report["provider"] == "mock"
    assert report["model"] == "mock-v1"
    assert report["audio_id"] == "consulta_ficticia_01"
    assert report["audio_duration_ms"] == 8000
    assert report["processing_time_ms"] == 42
    assert report["real_time_factor"] == 42 / 8000
    assert report["language"] == "es"
    assert report["succeeded"] is True
    assert report["transcription"]["word_count"] > 0
    assert len(report["transcription"]["segments"]) == 2
    assert report["capabilities"] == {"diarization": True, "timestamps": True, "confidence": True}
    # Sin reference.json/metadata.json: wer/terminology/negations/laterality
    # quedan sin calcular, pero diarization sí reporta lo detectable.
    assert report["metrics"]["wer"] is None
    assert report["metrics"]["terminology"] is None
    assert report["metrics"]["negations"] is None
    assert report["metrics"]["laterality"] is None
    assert report["metrics"]["diarization"]["detected_speaker_count"] == 2
    assert report["metrics"]["diarization"]["reference_speaker_count"] is None


def test_esquema_completo_con_reference_y_metadata():
    report = _build(_success_outcome(), reference=_REFERENCE, metadata=_METADATA)

    assert report["metrics"]["wer"]["value"] == 0.0
    assert report["metrics"]["terminology"]["accuracy"] == 1.0
    assert report["metrics"]["negations"]["passed"] == 1
    # "izquierdo" no aparece en la hipótesis: el caso se evalúa igualmente
    # pero queda como "not_detected" (ni pasa ni falla).
    assert report["metrics"]["laterality"]["passed"] == 0
    assert report["metrics"]["laterality"]["failed"] == 0
    assert report["metrics"]["laterality"]["details"][0]["result"] == "not_detected"
    assert report["metrics"]["diarization"]["reference_speaker_count"] == 2
    assert report["metrics"]["diarization"]["speaker_count_match"] is True
    assert report["metrics"]["diarization"]["attribution_accuracy"] == 1.0


def test_fallo_no_calcula_metricas_ni_transcripcion():
    report = _build(_failure_outcome(), reference=_REFERENCE, metadata=_METADATA)

    assert report["succeeded"] is False
    assert "no es un proveedor" in report["error"]
    assert report["transcription"]["text"] == ""
    assert report["transcription"]["word_count"] == 0
    assert report["metrics"]["wer"] is None
    assert report["metrics"]["diarization"] is None
    assert report["capabilities"] == {
        "diarization": False,
        "timestamps": False,
        "confidence": False,
    }


def test_real_time_factor_none_sin_duracion():
    outcome = _success_outcome()
    outcome = BenchmarkOutcome(
        provider=outcome.provider,
        audio_id=outcome.audio_id,
        ran_at=outcome.ran_at,
        response_time_ms=outcome.response_time_ms,
        result=TranscriptionResult(text="hola", language="es", duration_ms=None),
        error=None,
    )
    report = _build(outcome)
    assert report["real_time_factor"] is None


def test_write_report_usa_audio_id_como_nombre_de_fichero(tmp_path):
    report = _build(_success_outcome())
    output_path = write_report(
        report, results_dir=tmp_path, provider="mock", audio_id="consulta_ficticia_01"
    )

    assert output_path == tmp_path / "mock" / "consulta_ficticia_01.json"
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["provider"] == "mock"


def test_write_report_de_dos_proveedores_para_el_mismo_audio_no_se_pisan(tmp_path):
    mock_report = _build(_success_outcome())
    assemblyai_outcome = _success_outcome()
    assemblyai_outcome = BenchmarkOutcome(
        provider="assemblyai",
        audio_id=assemblyai_outcome.audio_id,
        ran_at=assemblyai_outcome.ran_at,
        response_time_ms=assemblyai_outcome.response_time_ms,
        result=assemblyai_outcome.result,
        error=None,
    )
    assemblyai_report = _build(assemblyai_outcome)

    write_report(mock_report, results_dir=tmp_path, provider="mock", audio_id="audio")
    write_report(assemblyai_report, results_dir=tmp_path, provider="assemblyai", audio_id="audio")

    assert (tmp_path / "mock" / "audio.json").exists()
    assert (tmp_path / "assemblyai" / "audio.json").exists()
