"""Fixtures clínicas sintéticas para la suite de aceptación de la Fase
6.4 (hito 6.4.5, RFC técnico de 6.4 §9). Todo el contenido es ficticio —
ver CLAUDE.md regla 1, ningún dato sanitario real.

Distinto del golden dataset de benchmark (`benchmark/generation_dataset/`,
Fase 6.2): esos casos comparan modelos reales vía OpenRouter; estos
transcripts alimentan tests deterministas con dobles Mock/scripted, sin
red — no se convierten al formato de ese dataset porque no hace falta
(RFC técnico de 6.4.5 §9, "no construyas un framework de dataset nuevo").
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.integrations.domain.anamnesis_generator import (
    ANAMNESIS_FIELDS,
    AnamnesisDraft,
    AnamnesisFieldStatus,
    AnamnesisFieldValue,
)
from app.integrations.domain.clinical_flags_generator import ClinicalFlagDraft
from app.integrations.domain.missing_information_generator import (
    MissingInfoItem,
    MissingInformationResult,
    MissingInformationTarget,
)
from app.integrations.domain.session_context import SessionContext
from app.integrations.domain.session_notes_generator import (
    SESSION_NOTES_BLOCKS,
    SessionNotesBlock,
    SessionNotesDraft,
)
from app.integrations.domain.transcription_provider import TranscriptionInput, TranscriptionResult
from app.integrations.mocks.mock_transcription_provider import FIXTURE_TRANSCRIPT_TEXT

# --- Transcripts sintéticos ---------------------------------------------------

#: Primera visita — reexporta el fixture ya usado por `MockTranscriptionProvider`
#: (Fase 4/5): contiene "acúfenos" (→ informado) y "Niega vértigo" (→
#: negado_explicitamente), no aborda antecedentes familiares ni exposición
#: a ruido (→ no_preguntado). Reutilizado, no duplicado.
FIRST_VISIT_TRANSCRIPT = FIXTURE_TRANSCRIPT_TEXT

#: Visita de seguimiento — contiene literalmente las 4 keywords que
#: `MockSessionNotesGenerator` reconoce (RFC técnico de 6.4.3 §6), para
#: poder ejercitar SESSION_NOTES con el Mock de producción real, sin
#: necesidad de un doble scripted.
FOLLOW_UP_TRANSCRIPT = (
    "AUDIOPROTESISTA: ¿Cómo ha ido con el audífono desde el ajuste?\n"
    "PACIENTE: Creo que ha mejorado bastante la comprensión en ambientes con ruido.\n"
    "AUDIOPROTESISTA: Perfecto, ajustamos el volumen un poco más esta sesión.\n"
    "PACIENTE: Aun así sigue notando pitidos por la noche.\n"
    "AUDIOPROTESISTA: Lo anoto. Programamos la próxima revisión en tres meses."
)

#: Referencia ambigua sin ningún hecho clínico concreto — para el caso L
#: (§2): un excerpt que solo exista en contexto longitudinal nunca puede
#: satisfacer el grounding de ESTA transcripción, porque literalmente no
#: contiene nada citable.
AMBIGUOUS_REFERENCE_TRANSCRIPT = (
    "AUDIOPROTESISTA: ¿Cómo se encuentra desde la última visita?\n"
    "PACIENTE: Pues seguimos igual que la última vez, sin cambios que destacar.\n"
    "AUDIOPROTESISTA: De acuerdo, lo dejamos anotado."
)

#: Frase que representa contenido EXCLUSIVO del contexto longitudinal
#: (nunca de la sesión actual) — usada como source_excerpt inválido en los
#: tests de separación evidencia/contexto (RFC técnico §7). Deliberadamente
#: ausente de todos los transcripts de este módulo.
LONGITUDINAL_ONLY_PHRASE = (
    "Exposición a ruido industrial documentada durante quince años consecutivos"
)

#: Corrección explícita dentro de la MISMA sesión — usado únicamente para
#: probar que el grounding acepta evidencia de corrección de la sesión
#: actual (RFC técnico §10). NO implica ninguna lógica de actualización
#: longitudinal: eso es `AnamnesisUpdateStep`, hito 6.5, deliberadamente
#: fuera de alcance aquí.
EXPLICIT_CORRECTION_TRANSCRIPT = (
    "AUDIOPROTESISTA: ¿Ha notado pitidos en los oídos?\n"
    "PACIENTE: Al principio le dije que no, pero quiero corregir eso: "
    "sí noto un pitido leve en el oído derecho desde hace una semana.\n"
    "AUDIOPROTESISTA: Entendido, lo anoto."
)
EXPLICIT_CORRECTION_EXCERPT = "sí noto un pitido leve en el oído derecho desde hace una semana"

#: Frase evasiva determinista (ver `app/ai_pipeline/domain/evasive.py`) —
#: usada para forzar un fallo real de MISSING_INFORMATION en los
#: escenarios de estado agregado del pipeline (§8), sin tocar schema ni
#: grounding (MISSING_INFORMATION no los tiene).
EVASIVE_SUGGESTED_QUESTION = "Como modelo de lenguaje, no puedo continuar con esta tarea."


# --- Builders de contenido válido por defecto ---------------------------------


def all_anamnesis_fields_no_preguntado() -> dict[str, AnamnesisFieldValue]:
    return {
        name: AnamnesisFieldValue(value="", status=AnamnesisFieldStatus.NO_PREGUNTADO)
        for name in ANAMNESIS_FIELDS
    }


def all_session_notes_blocks_empty() -> dict[str, SessionNotesBlock]:
    return {name: SessionNotesBlock(text="", source_excerpt=None) for name in SESSION_NOTES_BLOCKS}


def anamnesis_content_with_field(
    field_name: str, *, value: str, status: AnamnesisFieldStatus, source_excerpt: str | None
) -> dict[str, AnamnesisFieldValue]:
    fields = all_anamnesis_fields_no_preguntado()
    fields[field_name] = AnamnesisFieldValue(
        value=value, status=status, source_excerpt=source_excerpt
    )
    return fields


def session_notes_content_with_block(
    block_name: str, *, text: str, source_excerpt: str | None
) -> dict[str, SessionNotesBlock]:
    blocks = all_session_notes_blocks_empty()
    blocks[block_name] = SessionNotesBlock(text=text, source_excerpt=source_excerpt)
    return blocks


# --- Dobles de proveedor/generador, deterministas y sin red -------------------


@dataclass(slots=True)
class FixedTranscriptionProvider:
    """Devuelve siempre el mismo texto — a diferencia de
    `MockTranscriptionProvider` (fijo por diseño desde la Fase 5), permite
    controlar el transcript por escenario de test."""

    text: str

    async def transcribe(self, input: TranscriptionInput) -> TranscriptionResult:
        return TranscriptionResult(text=self.text, language="es", confidence=70)


@dataclass(slots=True)
class ScriptedAnamnesisGenerator:
    """Devuelve siempre el mismo `AnamnesisDraft` — para ejercitar
    combinaciones concretas de grounding/schema sin depender del
    reconocimiento de keywords de `MockAnamnesisGenerator`."""

    fields: dict[str, AnamnesisFieldValue]

    async def generate(self, transcript, missing_information, *, context: SessionContext):
        return AnamnesisDraft(fields=dict(self.fields))


@dataclass(slots=True)
class ScriptedSessionNotesGenerator:
    """Equivalente a `ScriptedAnamnesisGenerator` para SESSION_NOTES."""

    blocks: dict[str, SessionNotesBlock]

    async def generate(self, transcript, previous_anamnesis_context, *, context: SessionContext):
        return SessionNotesDraft(blocks=dict(self.blocks))


@dataclass(slots=True)
class EchoingSessionNotesGenerator:
    """Vuelca `previous_anamnesis_context` dentro de `text` de un bloque —
    usado únicamente para demostrar, de extremo a extremo, que el
    contenido correcto (la anamnesis previa "ganadora" por `approved_at`
    más reciente) llega hasta el generador. `source_excerpt` se toma del
    transcript ACTUAL (nunca del contexto previo): el contenido de `text`
    no está sujeto a grounding, solo `source_excerpt` — ver RFC técnico
    §7."""

    block_name: str
    current_transcript_excerpt: str

    async def generate(self, transcript, previous_anamnesis_context, *, context: SessionContext):
        blocks = all_session_notes_blocks_empty()
        blocks[self.block_name] = SessionNotesBlock(
            text=f"Contexto previo recibido: {previous_anamnesis_context or '(vacío)'}",
            source_excerpt=self.current_transcript_excerpt,
        )
        return SessionNotesDraft(blocks=blocks)


@dataclass(slots=True)
class ScriptedMissingInformationGenerator:
    """Devuelve items fijos por target — igual que
    `MockMissingInformationGenerator`, pero permite forzar una respuesta
    evasiva determinista para los escenarios de estado agregado (§8)."""

    items_by_target: dict[MissingInformationTarget, list[MissingInfoItem]] = field(
        default_factory=dict
    )

    async def generate(
        self, summary, clinical_flags: list[ClinicalFlagDraft], *, target, context: SessionContext
    ) -> MissingInformationResult:
        return MissingInformationResult(items=list(self.items_by_target.get(target, [])))


def evasive_missing_information_generator() -> ScriptedMissingInformationGenerator:
    """Fuerza `EVASIVE_OR_META_RESPONSE` en MISSING_INFORMATION,
    independientemente del target — usado para el escenario
    SKIPPED_DEPENDENCY de §8 (ANAMNESIS depende de MISSING_INFORMATION)."""
    evasive_item = [MissingInfoItem(topic="x", suggested_question=EVASIVE_SUGGESTED_QUESTION)]
    return ScriptedMissingInformationGenerator(
        items_by_target={
            MissingInformationTarget.ANAMNESIS_FIELDS: evasive_item,
            MissingInformationTarget.SESSION_NOTES_BLOCKS: evasive_item,
        }
    )
