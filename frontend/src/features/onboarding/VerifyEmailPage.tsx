import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ApiError } from '../../shared/api/client'
import { verifyEmail } from '../../shared/api/onboarding'

type VerificationStatus = 'verifying' | 'success' | 'error' | 'missing-token'

/** `GET ?token=` — enlace de `POST /clinics/signup` (ver
 * `OnboardingService.signup_clinic`, `link_path="verify-email"`). Verifica
 * automáticamente al montar: a diferencia de los formularios de esta misma
 * carpeta, aquí no hay ningún dato que pedir al usuario, solo confirmar el
 * token que ya trae la URL. */
export function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const [status, setStatus] = useState<VerificationStatus>(token ? 'verifying' : 'missing-token')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    if (!token) {
      setStatus('missing-token')
      return
    }
    let cancelled = false
    setStatus('verifying')
    verifyEmail(token)
      .then(() => {
        if (!cancelled) setStatus('success')
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setErrorMessage(
          error instanceof ApiError ? error.message : 'No se pudo verificar el email.',
        )
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [token])

  return (
    <section aria-label="Verificación de email">
      <h2>Verificación de email</h2>
      {status === 'verifying' && <p role="status">Verificando…</p>}
      {status === 'success' && (
        <>
          <p>Tu email ha quedado verificado. Ya puedes iniciar sesión.</p>
          <Link to="/">Ir a iniciar sesión</Link>
        </>
      )}
      {status === 'missing-token' && <p role="alert">Enlace no válido.</p>}
      {status === 'error' && <p role="alert">{errorMessage}</p>}
    </section>
  )
}
