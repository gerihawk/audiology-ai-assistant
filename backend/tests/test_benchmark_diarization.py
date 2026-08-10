"""Tests de la métrica de diarización (benchmark/metrics/diarization.py)."""

from __future__ import annotations

from benchmark.metrics.diarization import HypothesisSegment, evaluate_diarization
from benchmark.reference import Reference, ReferenceSegment, ReferenceSpeaker

_REFERENCE = Reference(
    language="es",
    speakers=[
        ReferenceSpeaker(id="audiologist", label="Audioprotesista"),
        ReferenceSpeaker(id="patient", label="Paciente"),
    ],
    segments=[
        ReferenceSegment(speaker="audiologist", text="Buenos días, ¿en qué puedo ayudarle?"),
        ReferenceSegment(speaker="patient", text="Escucho peor por el oído izquierdo."),
        ReferenceSegment(speaker="audiologist", text="¿Tiene acúfenos?"),
        ReferenceSegment(speaker="patient", text="Sí, un pitido constante."),
    ],
)


def test_speaker_count_coincide():
    hypothesis = [
        HypothesisSegment(speaker="A", text="Buenos días, ¿en qué puedo ayudarle?"),
        HypothesisSegment(speaker="B", text="Escucho peor por el oído izquierdo."),
        HypothesisSegment(speaker="A", text="¿Tiene acúfenos?"),
        HypothesisSegment(speaker="B", text="Sí, un pitido constante."),
    ]
    report = evaluate_diarization(_REFERENCE, hypothesis)
    assert report.reference_speaker_count == 2
    assert report.detected_speaker_count == 2
    assert report.speaker_count_match is True
    assert report.number_of_reference_segments == 4
    assert report.number_of_provider_segments == 4


def test_speaker_count_no_coincide_un_unico_speaker_detectado():
    # El caso real observado con AssemblyAI en la Fase 5: un único
    # speaker para todo el audio, pese a haber dos en la referencia.
    hypothesis = [
        HypothesisSegment(
            speaker="A",
            text=(
                "Buenos días, ¿en qué puedo ayudarle? Escucho peor por el oído "
                "izquierdo. ¿Tiene acúfenos? Sí, un pitido constante."
            ),
        )
    ]
    report = evaluate_diarization(_REFERENCE, hypothesis)
    assert report.reference_speaker_count == 2
    assert report.detected_speaker_count == 1
    assert report.speaker_count_match is False


def test_atribucion_perfecta_con_labels_bien_mapeados():
    hypothesis = [
        HypothesisSegment(speaker="speaker_1", text="Buenos días, ¿en qué puedo ayudarle?"),
        HypothesisSegment(speaker="speaker_2", text="Escucho peor por el oído izquierdo."),
        HypothesisSegment(speaker="speaker_1", text="¿Tiene acúfenos?"),
        HypothesisSegment(speaker="speaker_2", text="Sí, un pitido constante."),
    ]
    report = evaluate_diarization(_REFERENCE, hypothesis)
    assert report.attribution_accuracy == 1.0


def test_atribucion_con_labels_invertidos_sigue_siendo_correcta_por_mayoria():
    # El mapeo es por voto mayoritario, no por nombre — que el proveedor
    # llame "speaker_2" a quien la referencia llama "audiologist" no es un
    # error mientras sea consistente.
    hypothesis = [
        HypothesisSegment(speaker="speaker_2", text="Buenos días, ¿en qué puedo ayudarle?"),
        HypothesisSegment(speaker="speaker_1", text="Escucho peor por el oído izquierdo."),
        HypothesisSegment(speaker="speaker_2", text="¿Tiene acúfenos?"),
        HypothesisSegment(speaker="speaker_1", text="Sí, un pitido constante."),
    ]
    report = evaluate_diarization(_REFERENCE, hypothesis)
    assert report.attribution_accuracy == 1.0


def test_atribucion_imperfecta_penaliza_proporcionalmente():
    hypothesis = [
        HypothesisSegment(speaker="speaker_1", text="Buenos días, ¿en qué puedo ayudarle?"),
        # Este segmento debería ser "speaker_2" (patient) pero se etiqueta
        # como speaker_1 — error de atribución.
        HypothesisSegment(speaker="speaker_1", text="Escucho peor por el oído izquierdo."),
        HypothesisSegment(speaker="speaker_1", text="¿Tiene acúfenos?"),
        HypothesisSegment(speaker="speaker_2", text="Sí, un pitido constante."),
    ]
    report = evaluate_diarization(_REFERENCE, hypothesis)
    assert report.attribution_accuracy is not None
    assert 0.0 < report.attribution_accuracy < 1.0


def test_sin_hablantes_en_hipotesis_atribucion_es_none():
    hypothesis = [HypothesisSegment(speaker=None, text="todo el texto sin diarizar")]
    report = evaluate_diarization(_REFERENCE, hypothesis)
    assert report.detected_speaker_count == 0
    assert report.attribution_accuracy is None
