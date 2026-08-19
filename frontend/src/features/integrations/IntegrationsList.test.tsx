import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { IntegrationConfig } from '../../shared/api/types'
import { IntegrationsList } from './IntegrationsList'

function makeIntegration(overrides: Partial<IntegrationConfig> = {}): IntegrationConfig {
  return {
    id: 'integration-1',
    integration_name: 'patient_record',
    active_provider: 'mock',
    enabled: false,
    updated_by: 'u-1',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('IntegrationsList', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('no renderiza nada para un rol distinto de admin', () => {
    const { container } = render(<IntegrationsList devUserId="u-viewer" role="viewer" />)
    expect(container).toBeEmptyDOMElement()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('lista las integraciones para admin', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        items: [
          makeIntegration({ integration_name: 'patient_record' }),
          makeIntegration({ id: 'integration-2', integration_name: 'calendar', enabled: true }),
        ],
      }),
    )
    render(<IntegrationsList devUserId="u-admin" role="admin" />)

    expect(await screen.findByText('patient_record')).toBeInTheDocument()
    expect(screen.getByText('calendar')).toBeInTheDocument()
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/integrations')
  })

  it('muestra un mensaje cuando no hay integraciones', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [] }))
    render(<IntegrationsList devUserId="u-admin" role="admin" />)

    expect(await screen.findByText(/no hay integraciones configuradas/i)).toBeInTheDocument()
  })

  it('muestra el error del backend si falla la carga', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'forbidden', message: 'No autorizado.' } }, { status: 403 }),
    )
    render(<IntegrationsList devUserId="u-admin" role="admin" />)

    expect(await screen.findByText(/no autorizado/i)).toBeInTheDocument()
  })
})
