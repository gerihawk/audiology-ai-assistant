import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const initMock = vi.fn()
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
    breadcrumbsIntegrationMock.mockClear()
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
