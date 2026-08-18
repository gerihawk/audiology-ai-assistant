import { SESSION_TYPE_LABELS } from '../clinicalSessions/labels'
import type { SessionType } from '../../shared/api/types'

/** `session_type` es `str | null` en el contrato longitudinal
 * (`ClinicalRecordSessionEntryResponse`, ver clinical_record/api/schemas.py)
 * — `null` se representa como "Sin especificar" únicamente en presentación,
 * nunca se sustituye en los datos. Reutiliza las mismas etiquetas que
 * `clinicalSessions` en vez de duplicarlas. */
export function sessionTypeLabel(sessionType: string | null): string {
  if (!sessionType) return 'Sin especificar'
  return SESSION_TYPE_LABELS[sessionType as SessionType] ?? sessionType
}
