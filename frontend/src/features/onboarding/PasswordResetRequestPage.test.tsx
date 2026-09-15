import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithRouter } from '../../testUtils/renderWithRouter'
import { PasswordResetRequestPage } from './PasswordResetRequestPage'

describe('PasswordResetRequestPage', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('muestra el mismo mensaje de confirmación exista o no la cuenta (no-enumeración)', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
    const user = userEvent.setup()
    renderWithRouter(<PasswordResetRequestPage />)

    await user.type(screen.getByLabelText(/email/i), 'no-existe@test.local')
    await user.click(screen.getByRole('button', { name: /enviar enlace/i }))

    expect(await screen.findByText(/revisa tu email/i)).toBeInTheDocument()
    expect(screen.getByText('no-existe@test.local')).toBeInTheDocument()
    const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(requestInit.body as string)).toEqual({ email: 'no-existe@test.local' })
  })

  it('si la petición falla (p. ej. 500), muestra el error y no la pantalla de éxito', async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: 'internal_error', message: 'Error interno.' } }),
        {
          status: 500,
          headers: { 'content-type': 'application/json' },
        },
      ),
    )
    const user = userEvent.setup()
    renderWithRouter(<PasswordResetRequestPage />)

    await user.type(screen.getByLabelText(/email/i), 'valido@test.local')
    await user.click(screen.getByRole('button', { name: /enviar enlace/i }))

    expect(await screen.findByText('Error interno.')).toBeInTheDocument()
    expect(screen.queryByText(/revisa tu email/i)).not.toBeInTheDocument()
  })
})
