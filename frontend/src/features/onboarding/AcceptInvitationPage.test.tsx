import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithRouter } from '../../testUtils/renderWithRouter'
import { AcceptInvitationPage } from './AcceptInvitationPage'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('AcceptInvitationPage', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sin token en la URL: no muestra el formulario, solo "Enlace no válido"', () => {
    renderWithRouter(<AcceptInvitationPage />, { route: '/accept-invitation' })

    expect(screen.getByRole('alert')).toHaveTextContent(/enlace no válido/i)
    expect(screen.queryByLabelText(/tu nombre/i)).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('con token válido: envía token, nombre y contraseña, y muestra éxito', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    const user = userEvent.setup()
    renderWithRouter(<AcceptInvitationPage />, { route: '/accept-invitation?token=abc123' })

    await user.type(screen.getByLabelText(/tu nombre/i), 'Ana Pérez')
    await user.type(screen.getByLabelText(/contraseña/i), 'contraseña-nueva')
    await user.click(screen.getByRole('button', { name: /aceptar invitación/i }))

    expect(await screen.findByText(/cuenta creada/i)).toBeInTheDocument()
    const [url, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(String(url)).toContain('/invitations/abc123/accept')
    expect(JSON.parse(requestInit.body as string)).toEqual({
      display_name: 'Ana Pérez',
      new_password: 'contraseña-nueva',
    })
  })

  it('token ya usado/caducado (409): muestra el error del backend', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'conflict', message: 'Esta invitación ya no está pendiente.' } },
        { status: 409 },
      ),
    )
    const user = userEvent.setup()
    renderWithRouter(<AcceptInvitationPage />, { route: '/accept-invitation?token=usado' })

    await user.type(screen.getByLabelText(/tu nombre/i), 'Ana Pérez')
    await user.type(screen.getByLabelText(/contraseña/i), 'contraseña-nueva')
    await user.click(screen.getByRole('button', { name: /aceptar invitación/i }))

    expect(await screen.findByText(/esta invitación ya no está pendiente/i)).toBeInTheDocument()
  })
})
