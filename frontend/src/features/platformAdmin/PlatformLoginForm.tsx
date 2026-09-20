import { useState } from 'react'
import type { FormEvent } from 'react'
import { platformLogin } from './api'
import { usePlatformAuth } from './PlatformAuthContext'

/** Mismo patrón de formulario controlado que `shared/auth/LoginForm.tsx`
 * — sin los enlaces de "¿Has olvidado tu contraseña?"/"Crea una clínica":
 * no existen equivalentes para el operador de la plataforma (Fase 14):
 * no hay alta de operador por self-service (ver `app/platform_admin/cli.py`,
 * solo por CLI manual de Gerard) ni flujo de contraseña olvidada todavía. */
export function PlatformLoginForm() {
  const { signIn } = usePlatformAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setErrorMessage(null)
    try {
      const { access_token: accessToken } = await platformLogin(email, password)
      signIn(accessToken)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'No se pudo iniciar sesión.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={(event) => void handleSubmit(event)} aria-label="Iniciar sesión de operador">
      <h2>Acceso de operador de la plataforma</h2>
      <div>
        <label htmlFor="platform-login-email">Email</label>
        <input
          id="platform-login-email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
      </div>
      <div>
        <label htmlFor="platform-login-password">Contraseña</label>
        <input
          id="platform-login-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />
      </div>
      {errorMessage && <p role="alert">{errorMessage}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? 'Entrando…' : 'Entrar'}
      </button>
    </form>
  )
}
