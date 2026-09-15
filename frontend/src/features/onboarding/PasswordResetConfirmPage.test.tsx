import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithRouter } from '../../testUtils/renderWithRouter'
import { PasswordResetConfirmPage } from './PasswordResetConfirmPage'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('PasswordResetConfirmPage', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sin token en la URL: no muestra el formulario, solo "Enlace no válido"', () => {
    renderWithRouter(<PasswordResetConfirmPage />, { route: '/reset-password' })

    expect(screen.getByRole('alert')).toHaveTextContent(/enlace no válido/i)
    expect(screen.queryByLabelText(/nueva contraseña/i)).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('con token válido: envía token + nueva contraseña y muestra éxito', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    const user = userEvent.setup()
    renderWithRouter(<PasswordResetConfirmPage />, { route: '/reset-password?token=abc123' })

    await user.type(screen.getByLabelText(/nueva contraseña/i), 'contraseña-reseteada')
    await user.click(screen.getByRole('button', { name: /restablecer contraseña/i }))

    expect(await screen.findByText(/contraseña restablecida/i)).toBeInTheDocument()
    const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(requestInit.body as string)).toEqual({
      token: 'abc123',
      new_password: 'contraseña-reseteada',
    })
  })

  it('token ya usado/caducado (409): muestra el error del backend', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'conflict', message: 'Este enlace ya se ha usado o ha caducado.' } },
        { status: 409 },
      ),
    )
    const user = userEvent.setup()
    renderWithRouter(<PasswordResetConfirmPage />, { route: '/reset-password?token=usado' })

    await user.type(screen.getByLabelText(/nueva contraseña/i), 'contraseña-reseteada')
    await user.click(screen.getByRole('button', { name: /restablecer contraseña/i }))

    expect(await screen.findByText(/este enlace ya se ha usado o ha caducado/i)).toBeInTheDocument()
  })
})
