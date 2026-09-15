import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { InvitationSummary } from '../../shared/api/types'
import { InvitationsList } from './InvitationsList'

function makeInvitation(overrides: Partial<InvitationSummary> = {}): InvitationSummary {
  return {
    id: 'invitation-1',
    email: 'nuevo@example.com',
    role: 'audiologist',
    expires_at: '2099-01-01T00:00:00Z',
    created_at: '2026-01-01T00:00:00Z',
    is_expired: false,
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

describe('InvitationsList', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('lista las invitaciones pendientes', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        items: [
          makeInvitation({ email: 'ana@example.com', role: 'audiologist' }),
          makeInvitation({ id: 'invitation-2', email: 'luis@example.com', role: 'viewer' }),
        ],
      }),
    )
    render(<InvitationsList clinicId="clinic-1" devUserId="u-admin" reloadSignal={0} />)

    expect(await screen.findByText('ana@example.com')).toBeInTheDocument()
    expect(screen.getByText('luis@example.com')).toBeInTheDocument()
    expect(screen.getByText('Solo lectura')).toBeInTheDocument()
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/clinics/clinic-1/invitations')
  })

  it('muestra un mensaje cuando no hay invitaciones pendientes', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [] }))
    render(<InvitationsList clinicId="clinic-1" devUserId="u-admin" reloadSignal={0} />)

    expect(await screen.findByText(/no hay invitaciones pendientes/i)).toBeInTheDocument()
  })

  it('muestra el error del backend si falla la carga', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'forbidden', message: 'No autorizado.' } }, { status: 403 }),
    )
    render(<InvitationsList clinicId="clinic-1" devUserId="u-admin" reloadSignal={0} />)

    expect(await screen.findByText(/no autorizado/i)).toBeInTheDocument()
  })

  it('revoca una invitación y la retira de la lista tras recargar', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ items: [makeInvitation()] }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse({ items: [] }))
    const user = userEvent.setup()
    render(<InvitationsList clinicId="clinic-1" devUserId="u-admin" reloadSignal={0} />)

    expect(await screen.findByText('nuevo@example.com')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /revocar/i }))

    expect(await screen.findByText(/no hay invitaciones pendientes/i)).toBeInTheDocument()
    const [revokeUrl, revokeInit] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(String(revokeUrl)).toContain('/clinics/clinic-1/invitations/invitation-1')
    expect(revokeInit.method).toBe('DELETE')
  })
})
