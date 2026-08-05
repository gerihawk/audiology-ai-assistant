import { useState } from 'react'
import type { ClinicalSession } from '../../shared/api/types'
import { useDevUser } from '../../shared/devUser/DevUserContext'
import { ClinicalSessionDetail } from './ClinicalSessionDetail'
import { ClinicalSessionForm } from './ClinicalSessionForm'
import { ClinicalSessionList } from './ClinicalSessionList'
import { usePatientOptions } from './usePatientOptions'
import { useProfessionalOptions } from './useProfessionalOptions'

type View =
  | { name: 'list' }
  | { name: 'create' }
  | { name: 'edit'; session: ClinicalSession }
  | { name: 'detail'; session: ClinicalSession }

export function ClinicalSessionsPage() {
  const { currentUser, selectedUserId, status } = useDevUser()
  const [view, setView] = useState<View>({ name: 'list' })
  const [refreshToken, setRefreshToken] = useState(0)
  const { patients } = usePatientOptions(selectedUserId ?? '')
  const professionalOptions = useProfessionalOptions(currentUser)

  if (status === 'loading') {
    return <p role="status">Cargando…</p>
  }

  if (!selectedUserId) {
    return <p>Selecciona un usuario de desarrollo para gestionar sesiones clínicas.</p>
  }

  function goToList() {
    setRefreshToken((token) => token + 1)
    setView({ name: 'list' })
  }

  return (
    <section aria-label="Gestión de sesiones clínicas ficticias">
      {view.name === 'list' && (
        <ClinicalSessionList
          devUserId={selectedUserId}
          role={currentUser?.role}
          refreshToken={refreshToken}
          patientOptions={patients}
          professionalOptions={professionalOptions}
          onCreate={() => setView({ name: 'create' })}
          onSelect={(session) => setView({ name: 'detail', session })}
        />
      )}
      {view.name === 'create' && (
        <ClinicalSessionForm
          devUserId={selectedUserId}
          mode="create"
          currentUserId={currentUser?.id}
          role={currentUser?.role}
          patientOptions={patients}
          professionalOptions={professionalOptions}
          onDone={goToList}
          onCancel={goToList}
        />
      )}
      {view.name === 'edit' && (
        <ClinicalSessionForm
          devUserId={selectedUserId}
          mode="edit"
          session={view.session}
          currentUserId={currentUser?.id}
          role={currentUser?.role}
          patientOptions={patients}
          professionalOptions={professionalOptions}
          onDone={(updated) => setView({ name: 'detail', session: updated })}
          onCancel={() => setView({ name: 'detail', session: view.session })}
        />
      )}
      {view.name === 'detail' && (
        <ClinicalSessionDetail
          devUserId={selectedUserId}
          role={currentUser?.role}
          currentUserId={currentUser?.id}
          session={view.session}
          professionalOptions={professionalOptions}
          onBack={goToList}
          onEdit={() => setView({ name: 'edit', session: view.session })}
          onChanged={(updated) => setView({ name: 'detail', session: updated })}
        />
      )}
    </section>
  )
}
