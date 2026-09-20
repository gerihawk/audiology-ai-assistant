import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { PlatformClinic } from '../../shared/api/types'
import { PlatformClinicsPanel } from './PlatformClinicsPanel'
import { clearPlatformToken, setPlatformToken } from './tokenStore'

function makeClinic(overrides: Partial<PlatformClinic> = {}): PlatformClinic {
  return {
    id: 'c-1',
    name: 'Clínica Ejemplo',
    code: 'EJEMPLO',
    is_active: true,
    plan: 'basico',
    subscription_status: 'active',
    sessions_used_this_period: 12,
    current_period_started_at: '2026-09-01T00:00:00Z',
    created_at: '2026-01-01T00:00:00Z',
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

describe('PlatformClinicsPanel', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    setPlatformToken('token-operador')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    clearPlatformToken()
  })

  it('lista las clínicas devueltas por /platform/clinics', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [makeClinic()] }))

    render(<PlatformClinicsPanel />)

    const row = await screen.findByRole('row', { name: /clínica ejemplo/i })
    expect(within(row).getByText('EJEMPLO')).toBeInTheDocument()
    expect(within(row).getByText('Activa (active)')).toBeInTheDocument()
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/v1/platform/clinics')
  })

  it('al desactivar una clínica activa, hace PATCH con is_active=false y refleja el nuevo estado', async () => {
    const user = userEvent.setup()
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ items: [makeClinic()] }))
      .mockResolvedValueOnce(jsonResponse(makeClinic({ is_active: false })))

    render(<PlatformClinicsPanel />)

    const desactivarButton = await screen.findByRole('button', { name: 'Desactivar' })
    await user.click(desactivarButton)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Activar' })).toBeInTheDocument()
    })
    const [url, init] = fetchMock.mock.calls[1]
    expect(String(url)).toContain('/api/v1/platform/clinics/c-1')
    expect(init).toMatchObject({ method: 'PATCH' })
    expect(JSON.parse(init.body as string)).toEqual({ is_active: false })
    expect(screen.getByRole('row', { name: /clínica ejemplo/i })).toHaveTextContent('Desactivada')
  })

  it('muestra el error del backend si falla la carga de clínicas', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'unauthenticated', message: 'Token inválido.' } },
        { status: 401 },
      ),
    )

    render(<PlatformClinicsPanel />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Token inválido.')
  })
})
