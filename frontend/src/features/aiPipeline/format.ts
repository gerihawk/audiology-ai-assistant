export function formatDateTime(isoValue: string | null): string {
  if (!isoValue) return '—'
  const parsed = new Date(isoValue)
  if (Number.isNaN(parsed.getTime())) return isoValue
  return parsed.toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })
}

/** Umbral por debajo del cual se resalta la confianza como baja — nunca se
 * usa para ocultar ni para aprobar nada automáticamente, solo para
 * destacar visualmente qué artefactos merecen especial atención (ver
 * docs/ai-pipeline-architecture.md §8). */
export const LOW_CONFIDENCE_THRESHOLD = 60

export function isLowConfidence(confidence: number | null): boolean {
  return confidence !== null && confidence < LOW_CONFIDENCE_THRESHOLD
}
