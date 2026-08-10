import type { AIArtifactStatus, AIArtifactType } from '../../shared/api/types'

export const ARTIFACT_TYPE_LABELS: Record<AIArtifactType, string> = {
  transcript: 'Transcripción',
  summary: 'Resumen',
  clinical_flags: 'Señales de alerta',
  missing_information: 'Información ausente',
  anamnesis: 'Anamnesis estructurada',
}

/** Orden canónico del pipeline (ver docs/ai-pipeline-architecture.md §1.4):
 * transcript → {summary, clinical_flags} → missing_information → anamnesis.
 * El listado siempre se presenta en este orden, no en el orden (alfabético)
 * en que responde la API. */
export const ARTIFACT_TYPE_ORDER: AIArtifactType[] = [
  'transcript',
  'summary',
  'clinical_flags',
  'missing_information',
  'anamnesis',
]

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

/** Formato de respaldo para categorías de señales de alerta que no tengan
 * una etiqueta específica: `tinnitus_unilateral` → "Tinnitus unilateral". */
export function formatCategoryLabel(category: string): string {
  const withSpaces = category.replace(/_/g, ' ')
  return withSpaces.charAt(0).toUpperCase() + withSpaces.slice(1)
}
