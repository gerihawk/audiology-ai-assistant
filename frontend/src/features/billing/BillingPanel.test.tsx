import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BillingStatus } from '../../shared/api/types'
import { BillingPanel } from './BillingPanel'

function makeStatus(overrides: Partial<BillingStatus> = {}): BillingStatus {
  return {
    plan: 'basico',
    subscription_status: 'active',
    sessions_used_this_period: 10,
    included_sessions: 40,
    safety_cap_sessions: 80,
    has_stripe_customer: true,
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

describe('BillingPanel', () => {
  const fetchMock = vi.fn()
  let originalLocation: Location

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    // Sustituye `window.location` por un stub simple para poder hacer
    // aserciones sobre `.href` sin que jsdom intente navegar de verdad (lo
    // que generaría un "Not implemented: navigation" ruidoso en consola).
    originalLocation = window.location
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { href: '' } as unknown as Location,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    })
  })

  it('no renderiza nada para un rol distinto de admin', () => {
    const { container } = render(<BillingPanel devUserId="u-viewer" role="viewer" />)
    expect(container).toBeEmptyDOMElement()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('muestra el estado actual y el uso del periodo para admin', async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeStatus()))
    render(<BillingPanel devUserId="u-admin" role="admin" />)

    const estadoActual = await screen.findByRole('region', { name: 'Estado actual' })
    expect(within(estadoActual).getByText('Básico')).toBeInTheDocument()
    expect(within(estadoActual).getByText('active')).toBeInTheDocument()
    expect(
      screen.getByText(/uso de este periodo: 10 \/ 40 sesiones incluidas/i),
    ).toBeInTheDocument()
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/billing/status')
  })

  it('muestra el aviso de overage cuando el uso supera el tope incluido pero no el techo', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(makeStatus({ sessions_used_this_period: 50, included_sessions: 40 })),
    )
    render(<BillingPanel devUserId="u-admin" role="admin" />)

    expect(
      await screen.findByText(/en overage, facturado automáticamente hasta 80/i),
    ).toBeInTheDocument()
  })

  it('muestra el bloqueo cuando el uso supera el techo de seguridad', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        makeStatus({
          sessions_used_this_period: 90,
          included_sessions: 40,
          safety_cap_sessions: 80,
        }),
      ),
    )
    render(<BillingPanel devUserId="u-admin" role="admin" />)

    expect(
      await screen.findByText(/se ha superado el techo de uso incluido en el nivel contratado/i),
    ).toBeInTheDocument()
  })

  it('muestra el mensaje de gestión manual cuando la clínica no tiene plan de Stripe', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        makeStatus({
          plan: null,
          subscription_status: null,
          included_sessions: null,
          safety_cap_sessions: null,
          has_stripe_customer: false,
        }),
      ),
    )
    render(<BillingPanel devUserId="u-admin" role="admin" />)

    expect(
      await screen.findByText(/todavía no tiene un plan de stripe contratado/i),
    ).toBeInTheDocument()
  })

  it('muestra el error del backend si falla la carga del estado', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'forbidden', message: 'No autorizado.' } }, { status: 403 }),
    )
    render(<BillingPanel devUserId="u-admin" role="admin" />)

    expect(await screen.findByText(/no autorizado/i)).toBeInTheDocument()
  })

  it('al contratar un nivel, llama a checkout-session y redirige a la URL devuelta', async () => {
    const user = userEvent.setup()
    fetchMock
      .mockResolvedValueOnce(jsonResponse(makeStatus({ plan: null, has_stripe_customer: false })))
      .mockResolvedValueOnce(jsonResponse({ checkout_url: 'https://checkout.stripe.test/mock' }))
    render(<BillingPanel devUserId="u-admin" role="admin" />)

    await screen.findByText(/todavía no tiene un plan de stripe contratado/i)
    await user.click(screen.getAllByRole('button', { name: 'Contratar' })[0])

    await waitFor(() => expect(window.location.href).toBe('https://checkout.stripe.test/mock'))
    const [url, init] = fetchMock.mock.calls[1]
    expect(String(url)).toContain('/billing/checkout-session')
    expect(init).toMatchObject({ method: 'POST' })
    expect(JSON.parse(init.body as string)).toEqual({ plan: 'basico' })
  })

  it('al pulsar el botón del portal, llama a portal-session y redirige a la URL devuelta', async () => {
    const user = userEvent.setup()
    fetchMock
      .mockResolvedValueOnce(jsonResponse(makeStatus()))
      .mockResolvedValueOnce(jsonResponse({ portal_url: 'https://billing.stripe.test/mock' }))
    render(<BillingPanel devUserId="u-admin" role="admin" />)

    const portalButton = await screen.findByRole('button', {
      name: 'Gestionar método de pago / facturas',
    })
    await user.click(portalButton)

    await waitFor(() => expect(window.location.href).toBe('https://billing.stripe.test/mock'))
    const [url, init] = fetchMock.mock.calls[1]
    expect(String(url)).toContain('/billing/portal-session')
    expect(init).toMatchObject({ method: 'POST' })
  })

  it('deshabilita el botón del portal cuando la clínica no tiene cliente de Stripe', async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeStatus({ has_stripe_customer: false })))
    render(<BillingPanel devUserId="u-admin" role="admin" />)

    const portalButton = await screen.findByRole('button', {
      name: 'Gestionar método de pago / facturas',
    })
    expect(portalButton).toBeDisabled()
  })
})
