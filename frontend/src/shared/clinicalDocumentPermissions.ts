import type { Role } from './api/types'

// Refleja core/authorization.py: `ClinicalRecordAction` (lectura de la
// historia clínica longitudinal) y `ClinicalDocumentAction` (exportación,
// individual y longitudinal — mismo permiso para ambas, ver
// `ExportService.export()` y `ClinicalRecordService.export_record()`).
// Deliberadamente separado de `features/aiPipeline/permissions.ts`
// (AIArtifactAction/AIPipelineAction, con ownership por profesional) y de
// `features/clinicalSessions/permissions.ts`: ninguna de las dos reglas de
// aquí tiene ownership — es una vista/exportación de la clínica, no de
// "mis sesiones". El backend es la autoridad real; esto solo evita
// mostrar acciones que el servidor rechazaría.

export function canReadClinicalRecord(role: Role | undefined): boolean {
  return role === 'admin' || role === 'audiologist' || role === 'viewer'
}

export function canExportClinicalDocument(role: Role | undefined): boolean {
  return role === 'admin' || role === 'audiologist'
}
