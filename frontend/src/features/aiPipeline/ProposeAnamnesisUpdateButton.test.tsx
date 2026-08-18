import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProposeAnamnesisUpdateButton } from './ProposeAnamnesisUpdateButton'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('ProposeAnamnesisUpdateButton', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('no se muestra si el rol no tiene permiso', () => {
    const { container } = render(
      <ProposeAnamnesisUpdateButton
        devUserId="u-viewer"
        role="viewer"
        currentUserId="u-viewer"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onViewArtifact={vi.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('un audiologist no ve el botón sobre una sesión de otro profesional', () => {
    const { container } = render(
      <ProposeAnamnesisUpdateButton
        devUserId="u-audiologist"
        role="audiologist"
        currentUserId="u-audiologist"
        professionalId="u-otro"
        clinicalSessionId="s-1"
        onViewArtifact={vi.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('created=true: indica que se creó la propuesta, lista changed_fields y muestra el disclaimer', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        created: true,
        artifact_id: 'artifact-anamnesis-2',
        version_number: 1,
        status: 'review_pending',
        changed_fields: ['tinnitus', 'vertigo_o_inestabilidad'],
        ai_disclaimer: 'Contenido generado mediante IA.',
      }),
    )
    const user = userEvent.setup()

    render(
      <ProposeAnamnesisUpdateButton
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onViewArtifact={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /proponer actualización de anamnesis/i }))

    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent(/se ha creado una propuesta/i)
    expect(status).toHaveTextContent('Acúfenos (tinnitus)')
    expect(status).toHaveTextContent('Vértigo o inestabilidad')
    expect(status).toHaveTextContent('Contenido generado mediante IA.')
    expect(screen.getByRole('button', { name: /ver anamnesis propuesta/i })).toBeInTheDocument()
  })

  it('created=true: "Ver anamnesis propuesta" carga el artefacto real y lo entrega al padre', async () => {
    const proposalResponse = {
      created: true,
      artifact_id: 'artifact-anamnesis-2',
      version_number: 1,
      status: 'review_pending',
      changed_fields: ['tinnitus'],
      ai_disclaimer: 'Contenido generado mediante IA.',
    }
    const fetchedArtifact = {
      id: 'artifact-anamnesis-2',
      clinical_session_id: 's-1',
      artifact_type: 'anamnesis',
      status: 'review_pending',
      version_number: 1,
      content: {},
      confidence: 60,
      provider_name: 'mock',
      model_name: 'mock-v1',
      schema_version: 1,
      approved_by: null,
      approved_at: null,
      rejected_by: null,
      rejected_at: null,
      rejection_reason: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
      ai_disclaimer: 'Contenido generado mediante IA.',
      ruleset_disclaimer: null,
    }
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('propose-anamnesis-update')) return jsonResponse(proposalResponse)
      if (url.includes('/ai-artifacts/artifact-anamnesis-2')) return jsonResponse(fetchedArtifact)
      throw new Error(`Unhandled request: ${url}`)
    })
    const onViewArtifact = vi.fn()
    const user = userEvent.setup()

    render(
      <ProposeAnamnesisUpdateButton
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onViewArtifact={onViewArtifact}
      />,
    )

    await user.click(screen.getByRole('button', { name: /proponer actualización de anamnesis/i }))
    await user.click(await screen.findByRole('button', { name: /ver anamnesis propuesta/i }))

    expect(onViewArtifact).toHaveBeenCalledWith(fetchedArtifact)
  })

  it('created=false: dice explícitamente que no hubo cambios, nunca como error', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        created: false,
        artifact_id: null,
        version_number: null,
        status: null,
        changed_fields: [],
        ai_disclaimer: 'Contenido generado mediante IA.',
      }),
    )
    const user = userEvent.setup()

    render(
      <ProposeAnamnesisUpdateButton
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onViewArtifact={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /proponer actualización de anamnesis/i }))

    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent(/no se han propuesto cambios/i)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /ver anamnesis propuesta/i }),
    ).not.toBeInTheDocument()
  })

  it('409 por baseline obsoleto se muestra claramente, no como "Error desconocido"', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: 'conflict',
            message:
              'Ya existe una propuesta de actualización para esta sesión generada contra un ' +
              'baseline distinto del vigente. Resuelve la propuesta existente (apruébala, ' +
              'recházala o elimínala) antes de generar una nueva.',
          },
        },
        { status: 409 },
      ),
    )
    const user = userEvent.setup()

    render(
      <ProposeAnamnesisUpdateButton
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        clinicalSessionId="s-1"
        onViewArtifact={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /proponer actualización de anamnesis/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/conflicto/i)
    expect(alert).toHaveTextContent(/baseline distinto del vigente/i)
    expect(alert).not.toHaveTextContent(/error desconocido/i)
  })
})
