import { useState } from 'react'
import { archivePatient, restorePatient } from '../../shared/api/patients'
import type { DevUser, Patient, Role } from '../../shared/api/types'
import { PatientClinicalSessionsSection } from '../clinicalSessions/PatientClinicalSessionsSection'
import { canArchivePatient, canRestorePatient, canUpdatePatient } from './permissions'

interface PatientDetailProps {
  devUserId: string
  role: Role | undefined
  currentUserId: string | undefined
  professionalOptions: DevUser[]
  patient: Patient
  onBack: () => void
  onEdit: () => void
  onChanged: (patient: Patient) => void
}

export function PatientDetail({
  devUserId,
  role,
  currentUserId,
  professionalOptions,
  patient,
  onBack,
  onEdit,
  onChanged,
}: PatientDetailProps) {
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleArchive() {
    const confirmed = window.confirm(`¿Archivar al paciente ${patient.internal_code}?`)
    if (!confirmed) return
    setBusy(true)
    setActionError(null)
    try {
      const updated = await archivePatient(devUserId, patient.id)
      onChanged(updated)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'No se pudo archivar el paciente.')
    } finally {
      setBusy(false)
    }
  }

  async function handleRestore() {
    setBusy(true)
    setActionError(null)
    try {
      const updated = await restorePatient(devUserId, patient.id)
      onChanged(updated)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'No se pudo restaurar el paciente.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <button type="button" onClick={onBack}>
        Volver al listado
      </button>
      <h2>Paciente {patient.internal_code}</h2>
      {actionError && <p role="alert">{actionError}</p>}
      <dl>
        <dt>Nombre</dt>
        <dd>{patient.display_name ?? '—'}</dd>
        <dt>Año de nacimiento</dt>
        <dd>{patient.birth_year ?? '—'}</dd>
        <dt>Sexo</dt>
        <dd>{patient.sex ?? '—'}</dd>
        <dt>Idioma preferido</dt>
        <dd>{patient.preferred_language}</dd>
        <dt>Notas administrativas</dt>
        <dd>{patient.notes ?? '—'}</dd>
        <dt>Estado</dt>
        <dd>{patient.is_archived ? 'Archivado' : 'Activo'}</dd>
      </dl>
      <div>
        {!patient.is_archived && canUpdatePatient(role) && (
          <button type="button" onClick={onEdit}>
            Editar
          </button>
        )}
        {!patient.is_archived && canArchivePatient(role) && (
          <button type="button" onClick={handleArchive} disabled={busy}>
            Archivar
          </button>
        )}
        {patient.is_archived && canRestorePatient(role) && (
          <button type="button" onClick={handleRestore} disabled={busy}>
            Restaurar
          </button>
        )}
      </div>

      <PatientClinicalSessionsSection
        devUserId={devUserId}
        role={role}
        currentUserId={currentUserId}
        patient={patient}
        professionalOptions={professionalOptions}
      />
    </div>
  )
}
