import { useEffect, useState } from 'react'

type HealthState =
  { status: 'loading' } | { status: 'ok'; body: unknown } | { status: 'error'; message: string }

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export function BackendStatus() {
  const [health, setHealth] = useState<HealthState>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()

    async function checkHealth() {
      try {
        const response = await fetch(`${API_BASE_URL}/health`, { signal: controller.signal })
        if (!response.ok) {
          throw new Error(`El backend respondió con estado ${response.status}`)
        }
        const body: unknown = await response.json()
        setHealth({ status: 'ok', body })
      } catch (error) {
        if (controller.signal.aborted) return
        const message = error instanceof Error ? error.message : 'Error desconocido'
        setHealth({ status: 'error', message })
      }
    }

    void checkHealth()
    return () => controller.abort()
  }, [])

  return (
    <p>
      Backend: {health.status === 'loading' && 'comprobando…'}
      {health.status === 'ok' && <span data-testid="backend-status-ok">conectado</span>}
      {health.status === 'error' && <span role="alert">no disponible ({health.message})</span>}
    </p>
  )
}
