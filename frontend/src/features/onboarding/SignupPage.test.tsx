import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithRouter } from '../../testUtils/renderWithRouter'
import { SignupPage } from './SignupPage'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status: 201,
    headers: body === undefined ? {} : { 'content-type': 'application/json' },
    ...init,
  })
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/nombre de la clínica/i), 'Clínica Nueva')
  await user.type(screen.getByLabelText(/tu nombre/i), 'Admin Nuevo')
  await user.type(screen.getByLabelText(/^email$/i), 'nueva-clinica@test.local')
  await user.type(screen.getByLabelText(/contraseña/i), 'contraseña-de-doce')
  await user.click(screen.getByRole('button', { name: /crear cuenta/i }))
}

describe('SignupPage', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('tras un alta correcta, muestra la pantalla de "revisa tu email"', async () => {
    fetchMock.mockResolvedValue(jsonResponse(undefined))
    const user = userEvent.setup()
    renderWithRouter(<SignupPage />)

    await fillAndSubmit(user)

    expect(await screen.findByText(/revisa tu email/i)).toBeInTheDocument()
    expect(screen.getByText('nueva-clinica@test.local')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/clinics/signup'),
      expect.objectContaining({ method: 'POST' }),
    )
    const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(requestInit.body as string)).toEqual({
      clinic_name: 'Clínica Nueva',
      admin_email: 'nueva-clinica@test.local',
      admin_display_name: 'Admin Nuevo',
      admin_password: 'contraseña-de-doce',
    })
  })

  it('email duplicado (409): muestra el error asociado al campo admin_email', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: 'conflict',
            message: 'Ya existe una cuenta con ese email.',
            field: 'admin_email',
          },
        },
        { status: 409 },
      ),
    )
    const user = userEvent.setup()
    renderWithRouter(<SignupPage />)

    await fillAndSubmit(user)

    expect(await screen.findByText(/ya existe una cuenta con ese email/i)).toBeInTheDocument()
    expect(screen.queryByText(/revisa tu email/i)).not.toBeInTheDocument()
  })

  it('422 con `details`: reparte los mensajes por campo', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: 'validation_error',
            message: 'Error de validación.',
            details: [
              {
                loc: ['body', 'admin_password'],
                msg: 'La contraseña debe tener al menos 10 caracteres.',
                type: 'value_error',
              },
            ],
          },
        },
        { status: 422 },
      ),
    )
    const user = userEvent.setup()
    renderWithRouter(<SignupPage />)

    await fillAndSubmit(user)

    expect(
      await screen.findByText(/la contraseña debe tener al menos 10 caracteres/i),
    ).toBeInTheDocument()
  })
})
