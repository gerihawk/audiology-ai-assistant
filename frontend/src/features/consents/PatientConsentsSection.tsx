import { useState } from 'react'
import type { DevUser, Role } from '../../shared/api/types'
import { ConsentForm } from './ConsentForm'
import { ConsentList } from './ConsentList'
import { canCreateConsent, canReadConsents } from './permissions'

interface Props {
  devUserId: string
  role: Role | undefined
  patientId: string
  professionalOptions: DevUser[]
}

/** Sección mínima en la ficha del paciente (Fase 7.1) — no en la de
 * sesión: el consentimiento es a nivel paciente en esta ronda
 * (`clinical_session_id` siempre `null`, fuera de alcance). */
export function PatientConsentsSection({ devUserId, role, patientId, professionalOptions }: Props) {
  const [showForm, setShowForm] = useState(false)
  const [refreshToken, setRefreshToken] = useState(0)

  if (!canReadConsents(role)) return null

  function handleDone() {
    setRefreshToken((token) => token + 1)
    setShowForm(false)
  }

  return (
    <section aria-label="Consentimientos">
      <h3>Consentimientos</h3>

      <ConsentList
        devUserId={devUserId}
        patientId={patientId}
        refreshToken={refreshToken}
        professionalOptions={professionalOptions}
      />

      {canCreateConsent(role) && !showForm && (
        <button type="button" onClick={() => setShowForm(true)}>
          Registrar consentimiento
        </button>
      )}

      {canCreateConsent(role) && showForm && (
        <ConsentForm
          devUserId={devUserId}
          patientId={patientId}
          onDone={handleDone}
          onCancel={() => setShowForm(false)}
        />
      )}
    </section>
  )
}
