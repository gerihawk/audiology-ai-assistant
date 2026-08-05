import { useState } from 'react'
import type { Patient } from '../../shared/api/types'
import { useDevUser } from '../../shared/devUser/DevUserContext'
import { useProfessionalOptions } from '../clinicalSessions/useProfessionalOptions'
import { PatientDetail } from './PatientDetail'
import { PatientForm } from './PatientForm'
import { PatientList } from './PatientList'

type View =
  | { name: 'list' }
  | { name: 'create' }
  | { name: 'edit'; patient: Patient }
  | { name: 'detail'; patient: Patient }

export function PatientsPage() {
  const { currentUser, selectedUserId, status } = useDevUser()
  const [view, setView] = useState<View>({ name: 'list' })
  const [refreshToken, setRefreshToken] = useState(0)
  const professionalOptions = useProfessionalOptions(currentUser)

  if (status === 'loading') {
    return <p role="status">Cargando…</p>
  }

  if (!selectedUserId) {
    return <p>Selecciona un usuario de desarrollo para gestionar pacientes.</p>
  }

  function goToList() {
    setRefreshToken((token) => token + 1)
    setView({ name: 'list' })
  }

  return (
    <section aria-label="Gestión de pacientes ficticios">
      {view.name === 'list' && (
        <PatientList
          devUserId={selectedUserId}
          role={currentUser?.role}
          refreshToken={refreshToken}
          onCreate={() => setView({ name: 'create' })}
          onSelect={(patient) => setView({ name: 'detail', patient })}
        />
      )}
      {view.name === 'create' && (
        <PatientForm
          devUserId={selectedUserId}
          mode="create"
          onDone={goToList}
          onCancel={goToList}
        />
      )}
      {view.name === 'edit' && (
        <PatientForm
          devUserId={selectedUserId}
          mode="edit"
          patient={view.patient}
          onDone={(updated) => setView({ name: 'detail', patient: updated })}
          onCancel={() => setView({ name: 'detail', patient: view.patient })}
        />
      )}
      {view.name === 'detail' && (
        <PatientDetail
          devUserId={selectedUserId}
          role={currentUser?.role}
          currentUserId={currentUser?.id}
          professionalOptions={professionalOptions}
          patient={view.patient}
          onBack={goToList}
          onEdit={() => setView({ name: 'edit', patient: view.patient })}
          onChanged={(updated) => setView({ name: 'detail', patient: updated })}
        />
      )}
    </section>
  )
}
