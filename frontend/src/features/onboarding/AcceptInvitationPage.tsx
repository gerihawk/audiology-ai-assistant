import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError } from '../../shared/api/client'
import { acceptInvitation } from '../../shared/api/invitations'

/** Coincide con `MIN_PASSWORD_LENGTH` en
 * `app/onboarding/domain/normalization.py` — ver `SignupPage`. */
const MIN_PASSWORD_LENGTH = 10

/** `GET ?token=` — enlace de `POST /clinics/{clinic_id}/invitations` (ver
 * `InvitationService.create_invitation`, que construye
 * `{frontend_base_url}/accept-invitation?token=...`; mismo patrón de URL
 * que `PasswordResetConfirmPage` con `/reset-password`). A diferencia de
 * `VerifyEmailPage`, aquí hacen falta datos del usuario (nombre y
 * contraseña, ver `InvitationAcceptData` en el backend — `User.display_name`
 * es `NOT NULL` y no lo aporta quien invita), así que el token solo se usa
 * al enviar el formulario, no al montar. */
export function AcceptInvitationPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [displayName, setDisplayName] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!token) return
    setSubmitting(true)
    setFormError(null)
    try {
      await acceptInvitation(token, { display_name: displayName, new_password: newPassword })
      setSuccess(true)
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'No se pudo aceptar la invitación.')
    } finally {
      setSubmitting(false)
    }
  }

  if (!token) {
    return (
      <section aria-label="Aceptar invitación">
        <h2>Aceptar invitación</h2>
        <p role="alert">Enlace no válido.</p>
      </section>
    )
  }

  if (success) {
    return (
      <section aria-label="Cuenta creada">
        <h2>Cuenta creada</h2>
        <p>Ya puedes iniciar sesión con tu nueva contraseña.</p>
        <Link to="/">Ir a iniciar sesión</Link>
      </section>
    )
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} aria-label="Aceptar invitación">
      <h2>Aceptar invitación</h2>

      {formError && <p role="alert">{formError}</p>}

      <div>
        <label htmlFor="accept-invitation-display-name">Tu nombre</label>
        <input
          id="accept-invitation-display-name"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          required
        />
      </div>

      <div>
        <label htmlFor="accept-invitation-password">Contraseña</label>
        <input
          id="accept-invitation-password"
          type="password"
          autoComplete="new-password"
          value={newPassword}
          onChange={(event) => setNewPassword(event.target.value)}
          required
          minLength={MIN_PASSWORD_LENGTH}
          aria-describedby="accept-invitation-password-hint"
        />
        <p id="accept-invitation-password-hint">Al menos {MIN_PASSWORD_LENGTH} caracteres.</p>
      </div>

      <div>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Creando cuenta…' : 'Aceptar invitación'}
        </button>
      </div>
    </form>
  )
}
