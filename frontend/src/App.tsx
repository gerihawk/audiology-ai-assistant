import { useEffect, useState } from 'react'

type HealthState =
  { status: 'loading' } | { status: 'ok'; body: unknown } | { status: 'error'; message: string }

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

function App() {
  const [health, setHealth] = useState<HealthState>({ status: 'loading' })

  useEffect(() => {
    const controller = new AbortController()

    async function checkHealth() {
      try {
        const response = await fetch(`${API_BASE_URL}/health`, {
          signal: controller.signal,
        })
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
    <main>
      <h1>Audiology AI Assistant</h1>
      <p>Nombre provisional del producto. Estado actual: esqueleto técnico (Fase 1).</p>

      <section>
        <h2>Frontend</h2>
        <p>El frontend se ha cargado correctamente.</p>
      </section>

      <section>
        <h2>Backend (/health)</h2>
        {health.status === 'loading' && <p>Comprobando conexión con el backend…</p>}
        {health.status === 'ok' && (
          <p>
            Conectado. Respuesta: <code>{JSON.stringify(health.body)}</code>
          </p>
        )}
        {health.status === 'error' && (
          <p role="alert">No se pudo conectar con el backend: {health.message}</p>
        )}
      </section>
    </main>
  )
}

export default App
