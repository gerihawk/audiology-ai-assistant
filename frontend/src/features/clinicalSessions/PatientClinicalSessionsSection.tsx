import { useState } from 'react'
import type { ClinicalSession, DevUser, Patient, Role } from '../../shared/api/types'
import { ClinicalSessionDetail } from './ClinicalSessionDetail'
import { ClinicalSessionForm } from './ClinicalSessionForm'
import { ClinicalSessionList } from './ClinicalSessionList'

type View =
  | { name: 'list' }
  | { name: 'create' }
  | { name: 'edit'; session: ClinicalSession }
  | { name: 'detail'; session: ClinicalSession }

interface Props {
  devUserId: string
  role: Role | undefined
  currentUserId: string | undefined
  patient: Patient
  professionalOptions: DevUser[]
}

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
          onSelect={(session) => setView({ name: 'detail', session })}
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
      {view.name === 'edit' && (
        <ClinicalSessionForm
          devUserId={devUserId}
          mode="edit"
          session={view.session}
          currentUserId={currentUserId}
          role={role}
          patientOptions={[patient]}
          professionalOptions={professionalOptions}
          onDone={(updated) => setView({ name: 'detail', session: updated })}
          onCancel={() => setView({ name: 'detail', session: view.session })}
        />
      )}
      {view.name === 'detail' && (
        <ClinicalSessionDetail
          devUserId={devUserId}
          role={role}
          currentUserId={currentUserId}
          session={view.session}
          professionalOptions={professionalOptions}
          onBack={goToList}
          onEdit={() => setView({ name: 'edit', session: view.session })}
          onChanged={(updated) => setView({ name: 'detail', session: updated })}
        />
      )}
    </div>
  )
}
