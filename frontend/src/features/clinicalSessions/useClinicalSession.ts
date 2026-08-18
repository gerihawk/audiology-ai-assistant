import { useEffect, useState } from 'react'
import { getClinicalSession } from '../../shared/api/clinicalSessions'
import type { ClinicalSession } from '../../shared/api/types'

type ClinicalSessionState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; session: ClinicalSession }

/** Resuelve una sesión clínica por id para páginas montadas directamente
 * por URL (reload/deep-link). Ver `usePatient` para el mismo patrón. */
export function useClinicalSession(devUserId: string, sessionId: string) {
  const [state, setState] = useState<ClinicalSessionState>({ status: 'loading' })

  useEffect(() => {
    if (!devUserId) return
    let cancelled = false
    setState({ status: 'loading' })
    getClinicalSession(devUserId, sessionId)
      .then((session) => {
        if (!cancelled) setState({ status: 'ready', session })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            status: 'error',
            message:
              error instanceof Error ? error.message : 'No se pudo cargar la sesión clínica.',
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [devUserId, sessionId])

  const setSession = (session: ClinicalSession) => setState({ status: 'ready', session })

  return { ...state, setSession }
}
