import { useState } from 'react'
import type { DevUser, Patient, Role } from '../../shared/api/types'
import { ClinicalSessionForm } from './ClinicalSessionForm'
import { ClinicalSessionList } from './ClinicalSessionList'

type View = { name: 'list' } | { name: 'create' }

interface Props {
  devUserId: string
  role: Role | undefined
  currentUserId: string | undefined
  patient: Patient
  professionalOptions: DevUser[]
}

/** Lista embebida en el detalle de un paciente, con la creación fija a ese
 * paciente (`lockedPatient`). Ver detalle/editar navegan a la URL canónica
 * `/clinical-sessions/:id` — una sesión no tiene dos pantallas propias. */
export function PatientClinicalSessionsSection({
  devUserId,
  role,
  currentUserId,
  patient,
  professionalOptions,
}: Props) {
  const [view, setView] = useState<View>({ name: 'list' })
  const [refreshToken, setRefreshToken] = useState(0)

  function goToList() {
    setRefreshToken((token) => token + 1)
    setView({ name: 'list' })
  }

  return (
    <div>
      <h3>Sesiones clínicas de {patient.internal_code}</h3>

      {view.name === 'list' && (
        <ClinicalSessionList
          devUserId={devUserId}
          role={role}
          refreshToken={refreshToken}
          patientOptions={[patient]}
          professionalOptions={professionalOptions}
          lockedPatient={patient}
          onCreate={() => setView({ name: 'create' })}
        />
      )}
      {view.name === 'create' && (
        <ClinicalSessionForm
          devUserId={devUserId}
          mode="create"
          currentUserId={currentUserId}
          role={role}
          patientOptions={[patient]}
          professionalOptions={professionalOptions}
          lockedPatient={patient}
          onDone={goToList}
          onCancel={goToList}
        />
      )}
    </div>
  )
}
