import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { InvitationForm } from './InvitationForm'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('InvitationForm', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('envía email + rol y avisa a onInvited tras un 202', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 202 }))
    const onInvited = vi.fn()
    const user = userEvent.setup()
    render(<InvitationForm clinicId="clinic-1" devUserId="u-admin" onInvited={onInvited} />)

    await user.type(screen.getByLabelText(/email/i), 'nuevo@example.com')
    await user.selectOptions(screen.getByLabelText(/rol/i), 'viewer')
    await user.click(screen.getByRole('button', { name: /enviar invitación/i }))

    expect(await screen.findByText(/invitación enviada/i)).toBeInTheDocument()
    expect(onInvited).toHaveBeenCalledTimes(1)

    const [url, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/clinics/clinic-1/invitations')
    expect(JSON.parse(requestInit.body as string)).toEqual({
      email: 'nuevo@example.com',
      role: 'viewer',
    })
    expect((requestInit.headers as Record<string, string>)['X-Dev-User-Id']).toBe('u-admin')
  })

  it('muestra el error del backend si falla el envío', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'forbidden', message: 'No autorizado.' } }, { status: 403 }),
    )
    const onInvited = vi.fn()
    const user = userEvent.setup()
    render(<InvitationForm clinicId="clinic-1" devUserId="u-viewer" onInvited={onInvited} />)

    await user.type(screen.getByLabelText(/email/i), 'nuevo@example.com')
    await user.click(screen.getByRole('button', { name: /enviar invitación/i }))

    expect(await screen.findByText(/no autorizado/i)).toBeInTheDocument()
    expect(onInvited).not.toHaveBeenCalled()
  })
})
