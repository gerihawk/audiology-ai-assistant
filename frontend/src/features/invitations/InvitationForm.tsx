import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../../shared/api/client'
import { createInvitation } from '../../shared/api/invitations'
import type { InvitableRole } from '../../shared/api/types'

interface Props {
  clinicId: string
  devUserId: string
  onInvited: () => void
}

/** Formulario de invitación (Fase 12, hito 12.3) — envía email + rol a
 * `POST /clinics/{clinic_id}/invitations`. La respuesta 202 es siempre
 * idéntica exista o no ya una cuenta con ese email (no-enumeración, ver
 * `InvitationService.create_invitation`): el formulario nunca intenta
 * distinguir los dos casos, ni aquí ni en el mensaje de éxito. */
export function InvitationForm({ clinicId, devUserId, onInvited }: Props) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<InvitableRole>('audiologist')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setFormError(null)
    setSuccess(false)
    try {
      await createInvitation(clinicId, { email, role }, devUserId)
      setEmail('')
      setSuccess(true)
      onInvited()
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'No se pudo enviar la invitación.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} aria-label="Invitar a un compañero">
      <h3>Invitar a un compañero</h3>

      {formError && <p role="alert">{formError}</p>}
      {success && <p role="status">Invitación enviada.</p>}

      <div>
        <label htmlFor="invitation-email">Email</label>
        <input
          id="invitation-email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
      </div>

      <div>
        <label htmlFor="invitation-role">Rol</label>
        <select
          id="invitation-role"
          value={role}
          onChange={(event) => setRole(event.target.value as InvitableRole)}
        >
          <option value="audiologist">Audiólogo</option>
          <option value="viewer">Solo lectura</option>
        </select>
      </div>

      <div>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Enviando…' : 'Enviar invitación'}
        </button>
      </div>
    </form>
  )
}
