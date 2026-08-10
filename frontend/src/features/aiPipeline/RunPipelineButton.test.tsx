import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RunMockPipelineResponse } from '../../shared/api/types'
import { RunPipelineButton } from './RunPipelineButton'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function makeRunResult(overrides: Partial<RunMockPipelineResponse> = {}): RunMockPipelineResponse {
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

  it('un audiologist no ve el botón sobre una sesión de otro profesional', () => {
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

  it('ejecuta el mock pipeline y notifica el resultado', async () => {
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
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/clinical-sessions/s-1/run-mock-pipeline'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('muestra un error si la ejecución falla', async () => {
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

  it('bloquea el doble envío mientras se ejecuta', async () => {
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

    const button = screen.getByRole('button', { name: /run mock pipeline/i })
    await user.click(button)
    await user.click(button)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    resolveFetch(jsonResponse(makeRunResult()))
  })
})
