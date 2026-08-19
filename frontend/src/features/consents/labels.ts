import type { ConsentType } from '../../shared/api/types'

export const CONSENT_TYPE_LABELS: Record<ConsentType, string> = {
  grabacion_audio: 'Grabación de audio',
  procesamiento_ia: 'Procesamiento por IA',
  almacenamiento: 'Almacenamiento',
}

export const CONSENT_TYPES: ConsentType[] = [
  'grabacion_audio',
  'procesamiento_ia',
  'almacenamiento',
]
