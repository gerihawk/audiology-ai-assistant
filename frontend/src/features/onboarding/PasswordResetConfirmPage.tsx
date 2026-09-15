import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError } from '../../shared/api/client'
import { confirmPasswordReset } from '../../shared/api/onboarding'

/** Coincide con `MIN_PASSWORD_LENGTH` en
 * `app/onboarding/domain/normalization.py` — ver `SignupPage`. */
const MIN_PASSWORD_LENGTH = 10

/** `GET ?token=` — enlace de `POST /onboarding/password-reset/request`
 * (ver `OnboardingService.request_password_reset`,
 * `link_path="reset-password"`). A diferencia de `VerifyEmailPage`, aquí sí
 * hace falta un dato del usuario (la nueva contraseña), así que el token
 * solo se usa al enviar el formulario, no al montar. */
export function PasswordResetConfirmPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
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
      await confirmPasswordReset(token, newPassword)
      setSuccess(true)
    } catch (error) {
      setFormError(
        error instanceof ApiError ? error.message : 'No se pudo restablecer la contraseña.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  if (!token) {
    return (
      <section aria-label="Restablecer contraseña">
        <h2>Restablecer contraseña</h2>
        <p role="alert">Enlace no válido.</p>
      </section>
    )
  }

  if (success) {
    return (
      <section aria-label="Contraseña restablecida">
        <h2>Contraseña restablecida</h2>
        <p>Ya puedes iniciar sesión con tu nueva contraseña.</p>
        <Link to="/">Ir a iniciar sesión</Link>
      </section>
    )
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} aria-label="Restablecer contraseña">
      <h2>Restablecer contraseña</h2>

      {formError && <p role="alert">{formError}</p>}

      <div>
        <label htmlFor="reset-confirm-password">Nueva contraseña</label>
        <input
          id="reset-confirm-password"
          type="password"
          autoComplete="new-password"
          value={newPassword}
          onChange={(event) => setNewPassword(event.target.value)}
          required
          minLength={MIN_PASSWORD_LENGTH}
          aria-describedby="reset-confirm-password-hint"
        />
        <p id="reset-confirm-password-hint">Al menos {MIN_PASSWORD_LENGTH} caracteres.</p>
      </div>

      <div>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Guardando…' : 'Restablecer contraseña'}
        </button>
      </div>
    </form>
  )
}
