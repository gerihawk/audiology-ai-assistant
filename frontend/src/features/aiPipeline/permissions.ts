import type { Role } from '../../shared/api/types'

// Refleja core/authorization.py (AIPipelineAction/AIArtifactAction) del
// backend — el backend es la autoridad real, esto solo evita mostrar
// acciones que el servidor rechazaría. Un AIArtifact no tiene su propio
// "profesional responsable": hereda el de la ClinicalSession a la que
// pertenece, por eso todas estas funciones reciben `professionalId` (el
// de la sesión clínica), no un campo del propio artefacto.

function canActOnSession(
  role: Role | undefined,
  professionalId: string,
  currentUserId: string | undefined,
): boolean {
  if (role === 'admin') return true
  if (role === 'audiologist') return professionalId === currentUserId
  return false
}

/** Lectura (listar, ver detalle, ver versiones): sin restricción de
 * propiedad, igual que en clinical_sessions — cualquier rol autenticado
 * puede leer. */
export function canReadArtifacts(role: Role | undefined): boolean {
  return role === 'admin' || role === 'audiologist' || role === 'viewer'
}

export function canTriggerPipeline(
  role: Role | undefined,
  professionalId: string,
  currentUserId: string | undefined,
): boolean {
  return canActOnSession(role, professionalId, currentUserId)
}

export function canApprove(
  role: Role | undefined,
  professionalId: string,
  currentUserId: string | undefined,
): boolean {
  return canActOnSession(role, professionalId, currentUserId)
}

export function canReject(
  role: Role | undefined,
  professionalId: string,
  currentUserId: string | undefined,
): boolean {
  return canActOnSession(role, professionalId, currentUserId)
}

/** `AIArtifactAction.EDIT` en el backend — misma regla de propiedad que
 * approve/reject (`_AI_ARTIFACT_OWNERSHIP_REQUIRED` en `core/authorization.py`). */
export function canEdit(
  role: Role | undefined,
  professionalId: string,
  currentUserId: string | undefined,
): boolean {
  return canActOnSession(role, professionalId, currentUserId)
}

/** `propose-anamnesis-update` también autoriza vía `AIArtifactAction.EDIT`
 * (`AIPipelineService.propose_anamnesis_update`) — no existe una acción de
 * autorización propia distinta para esta operación. */
export function canProposeAnamnesisUpdate(
  role: Role | undefined,
  professionalId: string,
  currentUserId: string | undefined,
): boolean {
  return canActOnSession(role, professionalId, currentUserId)
}
