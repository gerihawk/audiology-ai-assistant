import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../shared/api/client'
import { requestPasswordReset } from '../../shared/api/onboarding'

/** `POST /onboarding/password-reset/request` siempre resuelve con 204 —
 * exista o no la cuenta (no-enumeración, ver
 * `OnboardingService.request_password_reset`). Esta página, en
 * consecuencia, muestra el mismo mensaje de éxito en los dos casos; nunca
 * intenta distinguirlos. */
export function PasswordResetRequestPage() {
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setFormError(null)
    try {
      await requestPasswordReset(email)
      setSubmitted(true)
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'No se pudo procesar la solicitud.')
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted) {
    return (
      <section aria-label="Solicitud de recuperación enviada">
        <h2>Revisa tu email</h2>
        <p>
          Si <strong>{email}</strong> tiene una cuenta, hemos enviado un enlace para restablecer la
          contraseña.
        </p>
        <Link to="/">Volver al inicio</Link>
      </section>
    )
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} aria-label="Recuperar contraseña">
      <h2>Recuperar contraseña</h2>

      {formError && <p role="alert">{formError}</p>}

      <div>
        <label htmlFor="reset-request-email">Email</label>
        <input
          id="reset-request-email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
      </div>

      <div>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Enviando…' : 'Enviar enlace de recuperación'}
        </button>
      </div>

      <p>
        <Link to="/">Volver al inicio</Link>
      </p>
    </form>
  )
}
