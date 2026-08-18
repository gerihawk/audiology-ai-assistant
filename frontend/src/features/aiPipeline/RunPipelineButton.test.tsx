import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RunPipelineResponse } from '../../shared/api/types'
import { RunPipelineButton } from './RunPipelineButton'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function makeRunResult(overrides: Partial<RunPipelineResponse> = {}): RunPipelineResponse {
  return {
    pipeline_run_id: 'run-1',
    status: 'completed',
    started_at: '2026-01-01T00:00:00Z',
    completed_at: '2026-01-01T00:00:05Z',
    artifacts: [],
    step_outcomes: [],
    ...overrides,
  }
}

describe('RunPipelineButton', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('no se muestra si el rol no tiene permiso para ejecutar el pipeline', () => {
    const { container } = render(
      <RunPipelineButton
        devUserId="u-viewer"
        role="viewer"
        currentUserId="u-viewer"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onCompleted={vi.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('un audiologist no ve los botones sobre una sesión de otro profesional', () => {
    const { container } = render(
      <RunPipelineButton
        devUserId="u-audiologist"
        role="audiologist"
        currentUserId="u-audiologist"
        professionalId="u-otro"
        clinicalSessionId="s-1"
        onCompleted={vi.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('muestra dos acciones claramente distinguidas: Mock y real', () => {
    render(
      <RunPipelineButton
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onCompleted={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /run mock pipeline/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run pipeline \(real\)/i })).toBeInTheDocument()
    // La distinción no es solo el nombre del botón: cada uno lleva su propia
    // explicación de riesgo, nunca un único botón ambiguo.
    expect(screen.getByText(/nunca usa proveedores externos ni genera coste/i)).toBeInTheDocument()
    expect(
      screen.getByText(/puede usar proveedores externos reales y generar coste/i),
    ).toBeInTheDocument()
  })

  it('Run Mock Pipeline llama únicamente a run-mock-pipeline, nunca a run-pipeline', async () => {
    const result = makeRunResult()
    fetchMock.mockResolvedValue(jsonResponse(result))
    const onCompleted = vi.fn()
    const user = userEvent.setup()

    render(
      <RunPipelineButton
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onCompleted={onCompleted}
      />,
    )

    await user.click(screen.getByRole('button', { name: /run mock pipeline/i }))

    await waitFor(() => expect(onCompleted).toHaveBeenCalledWith(result))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [calledUrl] = fetchMock.mock.calls[0]
    expect(String(calledUrl)).toContain('/api/v1/clinical-sessions/s-1/run-mock-pipeline')
    expect(String(calledUrl)).not.toMatch(/\/run-pipeline$/)
  })

  it('Run Pipeline (real) llama únicamente a run-pipeline, nunca al mock', async () => {
    const result = makeRunResult()
    fetchMock.mockResolvedValue(jsonResponse(result))
    const onCompleted = vi.fn()
    const user = userEvent.setup()

    render(
      <RunPipelineButton
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onCompleted={onCompleted}
      />,
    )

    await user.click(screen.getByRole('button', { name: /run pipeline \(real\)/i }))

    await waitFor(() => expect(onCompleted).toHaveBeenCalledWith(result))
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [calledUrl] = fetchMock.mock.calls[0]
    expect(String(calledUrl)).toContain('/api/v1/clinical-sessions/s-1/run-pipeline')
    expect(String(calledUrl)).not.toContain('run-mock-pipeline')
  })

  it('muestra un error inesperado (500) de forma genérica', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'internal_error', message: 'fallo simulado' } },
        { status: 500 },
      ),
    )
    const user = userEvent.setup()

    render(
      <RunPipelineButton
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onCompleted={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /run mock pipeline/i }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('un 409 en el pipeline real muestra el mensaje real del backend, sin reinterpretarlo', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: 'conflict',
            message: 'Falta consentimiento válido de procesamiento IA para este paciente.',
          },
        },
        { status: 409 },
      ),
    )
    const user = userEvent.setup()

    render(
      <RunPipelineButton
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onCompleted={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /run pipeline \(real\)/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/conflicto/i)
    expect(alert).toHaveTextContent(
      'Falta consentimiento válido de procesamiento IA para este paciente.',
    )
  })

  it('un 403 muestra un mensaje de no autorizado', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: 'forbidden',
            message:
              'Un audiologist solo puede disparar el pipeline sobre sus propias sesiones clínicas.',
          },
        },
        { status: 403 },
      ),
    )
    const user = userEvent.setup()

    render(
      <RunPipelineButton
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onCompleted={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /run mock pipeline/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/no autorizado/i)
  })

  it('un 422 muestra un mensaje de solicitud inválida', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'validation_error', message: 'Solicitud inválida.' } },
        { status: 422 },
      ),
    )
    const user = userEvent.setup()

    render(
      <RunPipelineButton
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onCompleted={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /run pipeline \(real\)/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/solicitud inválida/i)
  })

  it('bloquea el doble envío mientras se ejecuta cualquiera de los dos modos', async () => {
    let resolveFetch: (value: Response) => void = () => {}
    fetchMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve
      }),
    )
    const user = userEvent.setup()

    render(
      <RunPipelineButton
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onCompleted={vi.fn()}
      />,
    )

    const mockButton = screen.getByRole('button', { name: /run mock pipeline/i })
    const realButton = screen.getByRole('button', { name: /run pipeline \(real\)/i })
    await user.click(mockButton)
    await user.click(realButton)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    resolveFetch(jsonResponse(makeRunResult()))
  })
})
