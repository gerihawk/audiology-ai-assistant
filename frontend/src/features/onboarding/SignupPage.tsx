import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../shared/api/client'
import { signupClinic } from '../../shared/api/onboarding'

/** Coincide con `MIN_PASSWORD_LENGTH` en
 * `app/onboarding/domain/normalization.py` — solo para el hint/`minLength`
 * del campo; el backend sigue siendo la única fuente de verdad (422 con el
 * mensaje real si de todos modos se envía una contraseña corta). */
const MIN_PASSWORD_LENGTH = 10

export function SignupPage() {
  const [clinicName, setClinicName] = useState('')
  const [adminDisplayName, setAdminDisplayName] = useState('')
  const [adminEmail, setAdminEmail] = useState('')
  const [adminPassword, setAdminPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setFormError(null)
    setFieldErrors({})

    try {
      await signupClinic({
        clinic_name: clinicName,
        admin_email: adminEmail,
        admin_display_name: adminDisplayName,
        admin_password: adminPassword,
      })
      setSubmittedEmail(adminEmail)
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === 'conflict' && error.field) {
          setFieldErrors({ [error.field]: error.message })
        } else if (error.code === 'validation_error' && error.details) {
          const next: Record<string, string> = {}
          for (const detail of error.details) {
            const field = detail.loc?.[detail.loc.length - 1]
            if (typeof field === 'string') next[field] = detail.msg
          }
          setFieldErrors(next)
        } else {
          setFormError(error.message)
        }
      } else {
        setFormError('No se pudo crear la cuenta.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (submittedEmail) {
    return (
      <section aria-label="Registro completado">
        <h2>Revisa tu email</h2>
        <p>
          Hemos enviado un enlace de verificación a <strong>{submittedEmail}</strong>. Ábrelo para
          activar tu cuenta antes de iniciar sesión.
        </p>
        <Link to="/">Volver al inicio</Link>
      </section>
    )
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} aria-label="Crear cuenta de clínica">
      <h2>Crear cuenta de clínica</h2>

      {formError && <p role="alert">{formError}</p>}

      <div>
        <label htmlFor="signup-clinic-name">Nombre de la clínica</label>
        <input
          id="signup-clinic-name"
          value={clinicName}
          onChange={(event) => setClinicName(event.target.value)}
          required
          aria-invalid={Boolean(fieldErrors.clinic_name)}
          aria-describedby={fieldErrors.clinic_name ? 'signup-clinic-name-error' : undefined}
        />
        {fieldErrors.clinic_name && (
          <p id="signup-clinic-name-error" role="alert">
            {fieldErrors.clinic_name}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="signup-admin-display-name">Tu nombre</label>
        <input
          id="signup-admin-display-name"
          value={adminDisplayName}
          onChange={(event) => setAdminDisplayName(event.target.value)}
          required
          aria-invalid={Boolean(fieldErrors.admin_display_name)}
          aria-describedby={
            fieldErrors.admin_display_name ? 'signup-admin-display-name-error' : undefined
          }
        />
        {fieldErrors.admin_display_name && (
          <p id="signup-admin-display-name-error" role="alert">
            {fieldErrors.admin_display_name}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="signup-admin-email">Email</label>
        <input
          id="signup-admin-email"
          type="email"
          autoComplete="username"
          value={adminEmail}
          onChange={(event) => setAdminEmail(event.target.value)}
          required
          aria-invalid={Boolean(fieldErrors.admin_email)}
          aria-describedby={fieldErrors.admin_email ? 'signup-admin-email-error' : undefined}
        />
        {fieldErrors.admin_email && (
          <p id="signup-admin-email-error" role="alert">
            {fieldErrors.admin_email}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="signup-admin-password">Contraseña</label>
        <input
          id="signup-admin-password"
          type="password"
          autoComplete="new-password"
          value={adminPassword}
          onChange={(event) => setAdminPassword(event.target.value)}
          required
          minLength={MIN_PASSWORD_LENGTH}
          aria-invalid={Boolean(fieldErrors.admin_password)}
          aria-describedby={
            fieldErrors.admin_password
              ? 'signup-admin-password-error'
              : 'signup-admin-password-hint'
          }
        />
        {fieldErrors.admin_password ? (
          <p id="signup-admin-password-error" role="alert">
            {fieldErrors.admin_password}
          </p>
        ) : (
          <p id="signup-admin-password-hint">Al menos {MIN_PASSWORD_LENGTH} caracteres.</p>
        )}
      </div>

      <div>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Creando cuenta…' : 'Crear cuenta'}
        </button>
      </div>

      <p>
        ¿Ya tienes cuenta? <Link to="/">Inicia sesión</Link>
      </p>
    </form>
  )
}
