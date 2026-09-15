import { screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithRouter } from '../../testUtils/renderWithRouter'
import { VerifyEmailPage } from './VerifyEmailPage'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('VerifyEmailPage', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sin token en la URL: no llama a la API y muestra "Enlace no válido"', () => {
    renderWithRouter(<VerifyEmailPage />, { route: '/verify-email' })

    expect(screen.getByRole('alert')).toHaveTextContent(/enlace no válido/i)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('con token válido: verifica automáticamente al montar y muestra éxito', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

    renderWithRouter(<VerifyEmailPage />, { route: '/verify-email?token=abc123' })

    expect(await screen.findByText(/tu email ha quedado verificado/i)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/onboarding/verify-email'),
      expect.objectContaining({ method: 'POST' }),
    )
    const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(requestInit.body as string)).toEqual({ token: 'abc123' })
  })

  it('con token inválido/caducado: muestra el mensaje de error del backend', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'not_found', message: 'Enlace no válido.' } }, { status: 404 }),
    )

    renderWithRouter(<VerifyEmailPage />, { route: '/verify-email?token=caducado' })

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Enlace no válido.')
    })
  })
})
