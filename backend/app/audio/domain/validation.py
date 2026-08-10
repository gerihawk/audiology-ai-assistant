"""Validación de subida de audio (tamaño/duración/extensión/MIME).

Ver docs/data-model.md §2 (`audio_recordings`) y docs/architecture.md §3
(`audio`). Devuelve el motivo de fallo en vez de lanzar una excepción: una
subida inválida sigue transicionando `uploaded -> failed` (con
`failure_reason`), no se descarta en silencio — mismo criterio que
`AIGenerationRun` ante un fallo de proveedor (ver
docs/ai-pipeline-architecture.md §8).

No extrae la duración real del binario (fuera de alcance de esta fase,
deuda técnica documentada en docs/transcription-benchmark.md): confía en
`duration_seconds` proporcionado por el cliente en la subida, y solo
valida que esté dentro del rango configurado.
"""

from __future__ import annotations

from app.core.config import Settings


def find_upload_validation_error(
    *,
    mime_type: str,
    extension: str,
    size_bytes: int,
    duration_seconds: int,
    settings: Settings,
) -> str | None:
    normalized_extension = extension.lstrip(".").lower()
    if normalized_extension not in settings.audio_allowed_extensions_list:
        return (
            f"Extensión '{extension}' no permitida. Extensiones válidas: "
            f"{', '.join(settings.audio_allowed_extensions_list)}."
        )
    if mime_type not in settings.audio_allowed_mime_types_list:
        return (
            f"Tipo MIME '{mime_type}' no permitido. Tipos válidos: "
            f"{', '.join(settings.audio_allowed_mime_types_list)}."
        )
    max_bytes = settings.audio_max_size_mb * 1024 * 1024
    if size_bytes <= 0:
        return "El fichero de audio está vacío."
    if size_bytes > max_bytes:
        return f"El audio supera el tamaño máximo permitido ({settings.audio_max_size_mb} MB)."
    if duration_seconds <= 0:
        return "La duración del audio debe ser mayor que 0."
    if duration_seconds > settings.audio_max_duration_seconds:
        return (
            f"El audio supera la duración máxima permitida "
            f"({settings.audio_max_duration_seconds} s)."
        )
    return None
