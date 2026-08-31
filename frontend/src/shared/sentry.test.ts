import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Stub de las integraciones por defecto reales de Sentry (recorte — el SDK
// real trae ~11) usado por el test de regresión de más abajo: basta con
// que 'GlobalHandlers' (captura window.onerror/unhandledrejection) y
// 'Dedupe' representen "cualquier integración por defecto ajena a
// Breadcrumbs" para detectar si `initSentry()` las descarta sin querer.
const DEFAULT_INTEGRATIONS_STUB = [
  { name: 'GlobalHandlers' },
  { name: 'Dedupe' },
  { name: 'Breadcrumbs' },
]

// Simula lo que hace el `Sentry.init` real con la opción `integrations`:
// si es una función, se invoca con los defaults reales del SDK y se usa
// el resultado; si es un array, se usa tal cual (mismo defecto que
// motivó el bug — un array propio nunca ve los defaults). Ver
// docs/privacy-and-security.md — no aplica aquí, pero el comentario de
// sentry.ts documenta por qué la forma función es la única segura.
let lastResolvedIntegrations: unknown
function resolveIntegrations(options: Record<string, unknown>): void {
  lastResolvedIntegrations =
    typeof options.integrations === 'function'
      ? (options.integrations as (defaults: unknown[]) => unknown[])(DEFAULT_INTEGRATIONS_STUB)
      : options.integrations
}

const initMock = vi.fn(resolveIntegrations)
const breadcrumbsIntegrationMock = vi.fn((options: unknown) => ({
  name: 'Breadcrumbs',
  options,
}))

vi.mock('@sentry/react', () => ({
  init: initMock,
  breadcrumbsIntegration: breadcrumbsIntegrationMock,
}))

describe('initSentry', () => {
  beforeEach(() => {
    initMock.mockReset()
    initMock.mockImplementation(resolveIntegrations)
    breadcrumbsIntegrationMock.mockClear()
    lastResolvedIntegrations = undefined
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('no inicializa Sentry si VITE_SENTRY_DSN no está configurada', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', '')
    const { initSentry } = await import('./sentry')

    initSentry()

    expect(initMock).not.toHaveBeenCalled()
  })

  it('inicializa sin tracing/replay cuando VITE_SENTRY_DSN sí está configurada', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://public@example.ingest.sentry.io/1')
    const { initSentry } = await import('./sentry')

    initSentry()

    expect(initMock).toHaveBeenCalledTimes(1)
    const options = initMock.mock.calls[0][0]
    expect(options.tracesSampleRate).toBe(0)
    expect(options.sendDefaultPii).toBe(false)
    // Único elemento de `integrations`: nunca replayIntegration/tracing.
    expect(breadcrumbsIntegrationMock).toHaveBeenCalledWith({ console: false })
  })

  it('pasa VITE_SENTRY_RELEASE como release cuando está definida', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://public@example.ingest.sentry.io/1')
    vi.stubEnv('VITE_SENTRY_RELEASE', 'abc123')
    const { initSentry } = await import('./sentry')

    initSentry()

    const options = initMock.mock.calls[0][0]
    expect(options.release).toBe('abc123')
  })

  it('regresión: integrations debe ser función — un array sustituiría GlobalHandlers/Dedupe por defecto', async () => {
    // Bug real de producción (Fase 10.6): `integrations: [breadcrumbsIntegration(...)]`
    // (array literal) nunca ve los defaults del SDK real — solo la forma
    // función los recibe y permite sustituir Breadcrumbs sin perder el
    // resto (GlobalHandlers, que captura window.onerror/unhandledrejection,
    // entre ellos). Un throw real en producción no generó ningún evento.
    vi.stubEnv('VITE_SENTRY_DSN', 'https://public@example.ingest.sentry.io/1')
    const { initSentry } = await import('./sentry')

    initSentry()

    const resolved = lastResolvedIntegrations as Array<{ name: string; options?: unknown }>
    const names = resolved.map((integration) => integration.name)

    expect(names).toContain('GlobalHandlers')
    expect(names).toContain('Dedupe')
    expect(names.filter((name) => name === 'Breadcrumbs')).toHaveLength(1)
    const ourBreadcrumbs = resolved.find((integration) => integration.name === 'Breadcrumbs')
    expect(ourBreadcrumbs?.options).toEqual({ console: false })
  })
})

describe('beforeSend', () => {
  it('elimina datos de formulario/estado que pudieran colarse en el evento', async () => {
    const { beforeSend } = await import('./sentry')

    // Campo PHI/PII real simulado: nombre de paciente (patients.display_name)
    // y notas administrativas de texto libre, colados en `request.data`
    // (docs/privacy-and-security.md §2).
    const event = {
      request: {
        data: { display_name: 'Juana Pérez', notes: 'refiere tinnitus unilateral' },
        cookies: { session: 'abc' },
        headers: {
          Authorization: 'Bearer secreto',
          'Content-Type': 'application/json',
          'X-Request-ID': 'req-123',
        },
      },
      extra: { formValues: { display_name: 'Juana Pérez' } },
    } as unknown as Parameters<typeof beforeSend>[0]

    const result = beforeSend(event)

    expect(result).not.toBeNull()
    expect(result?.request?.data).toBeUndefined()
    expect(result?.request?.cookies).toBeUndefined()
    expect(result?.request?.headers).toEqual({
      'Content-Type': 'application/json',
      'X-Request-ID': 'req-123',
    })
    expect(result?.extra).toBeUndefined()
  })
})

describe('beforeBreadcrumb', () => {
  it('descarta breadcrumbs de tipo console', async () => {
    const { beforeBreadcrumb } = await import('./sentry')

    const dropped = beforeBreadcrumb({
      category: 'console',
      data: { arguments: ['nombre del paciente: Juana Pérez'] },
    })
    const kept = beforeBreadcrumb({ category: 'fetch', data: { method: 'GET', url: '/patients' } })

    expect(dropped).toBeNull()
    expect(kept).not.toBeNull()
  })
})
