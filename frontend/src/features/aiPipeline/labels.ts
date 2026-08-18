import type { AIArtifactStatus, AIArtifactType } from '../../shared/api/types'

export const ARTIFACT_TYPE_LABELS: Record<AIArtifactType, string> = {
  transcript: 'Transcripción',
  summary: 'Resumen',
  patient_summary: 'Resumen para el paciente',
  clinical_flags: 'Señales de alerta',
  missing_information: 'Información ausente',
  anamnesis: 'Anamnesis estructurada',
  session_notes: 'Notas de la sesión',
}

/** Orden canónico del pipeline — espejo exacto de `PIPELINE_STEP_ORDER` en
 * `backend/app/ai_pipeline/domain/entities.py`: transcript → summary →
 * patient_summary → clinical_flags → missing_information → anamnesis →
 * session_notes. El listado siempre se presenta en este orden, no en el
 * orden (alfabético) en que responde la API. */
export const ARTIFACT_TYPE_ORDER: AIArtifactType[] = [
  'transcript',
  'summary',
  'patient_summary',
  'clinical_flags',
  'missing_information',
  'anamnesis',
  'session_notes',
]

/** Etiqueta segura para un `artifact_type`: los 7 valores de
 * `AIArtifactType` siempre tienen entrada en `ARTIFACT_TYPE_LABELS`, pero
 * el valor real viaja como JSON sin validar en tiempo de ejecución — si el
 * backend llegara a añadir un tipo nuevo antes de que el frontend lo
 * conozca, esto evita una tarjeta con etiqueta en blanco (nunca silenciosa). */
export function getArtifactTypeLabel(artifactType: AIArtifactType): string {
  return ARTIFACT_TYPE_LABELS[artifactType] ?? `Tipo desconocido (${String(artifactType)})`
}

/** Posición segura en el orden canónico: un tipo no reconocido se envía al
 * final del listado (nunca al principio, que es lo que producía
 * `indexOf(...) === -1` sin este guardado). */
export function getArtifactTypeOrder(artifactType: AIArtifactType): number {
  const index = ARTIFACT_TYPE_ORDER.indexOf(artifactType)
  return index === -1 ? Number.POSITIVE_INFINITY : index
}

export const ARTIFACT_STATUS_LABELS: Record<AIArtifactStatus, string> = {
  review_pending: 'Pendiente de revisión',
  approved: 'Aprobado',
  rejected: 'Rechazado',
}

/** Los 20 campos rellenables por IA de la anamnesis (ver docs/data-model.md
 * §3, campos 1-20; 21 y 22 no son contenido generado por IA). */
export const ANAMNESIS_FIELD_LABELS: Record<string, string> = {
  motivo_consulta: 'Motivo de consulta',
  percepcion_subjetiva_perdida_auditiva: 'Percepción subjetiva de pérdida auditiva',
  inicio_y_evolucion: 'Inicio y evolución',
  lateralidad: 'Lateralidad',
  antecedentes_familiares: 'Antecedentes familiares',
  antecedentes_otologicos: 'Antecedentes otológicos',
  infecciones: 'Infecciones',
  cirugias: 'Cirugías',
  exposicion_ruido: 'Exposición a ruido',
  medicacion_ototoxica_declarada: 'Medicación ototóxica declarada',
  tinnitus: 'Acúfenos (tinnitus)',
  vertigo_o_inestabilidad: 'Vértigo o inestabilidad',
  otalgia: 'Otalgia',
  otorrea: 'Otorrea',
  sensacion_plenitud: 'Sensación de plenitud',
  dificultades_comprension: 'Dificultades de comprensión',
  situaciones_auditivas_problematicas: 'Situaciones auditivas problemáticas',
  uso_previo_audifonos: 'Uso previo de audífonos',
  expectativas: 'Expectativas',
  impacto_social_laboral_familiar: 'Impacto social, laboral y familiar',
}

export type AnamnesisFieldStatus =
  'informado' | 'negado_explicitamente' | 'no_preguntado' | 'no_determinado'

export const ANAMNESIS_FIELD_STATUS_LABELS: Record<AnamnesisFieldStatus, string> = {
  informado: 'Informado',
  negado_explicitamente: 'Negado explícitamente',
  no_preguntado: 'No preguntado',
  no_determinado: 'No determinado',
}

/** Los 4 bloques cerrados de SESSION_NOTES (ver
 * backend/app/integrations/domain/session_notes_generator.py
 * `SESSION_NOTES_BLOCKS`) — mismo orden que el backend. */
export const SESSION_NOTES_BLOCK_ORDER = [
  'changes_since_last_visit',
  'device_adjustments',
  'patient_reported_issues',
  'next_steps',
] as const

export const SESSION_NOTES_BLOCK_LABELS: Record<
  (typeof SESSION_NOTES_BLOCK_ORDER)[number],
  string
> = {
  changes_since_last_visit: 'Cambios desde la última visita',
  device_adjustments: 'Ajustes del dispositivo',
  patient_reported_issues: 'Molestias referidas por el paciente',
  next_steps: 'Próximos pasos',
}

/** Formato de respaldo para categorías de señales de alerta que no tengan
 * una etiqueta específica: `tinnitus_unilateral` → "Tinnitus unilateral". */
export function formatCategoryLabel(category: string): string {
  const withSpaces = category.replace(/_/g, ' ')
  return withSpaces.charAt(0).toUpperCase() + withSpaces.slice(1)
}
