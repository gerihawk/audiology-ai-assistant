import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AIArtifact } from '../../shared/api/types'
import { ArtifactActions } from './ArtifactActions'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function makeArtifact(overrides: Partial<AIArtifact> = {}): AIArtifact {
  return {
    id: 'artifact-1',
    clinical_session_id: 's-1',
    artifact_type: 'summary',
    status: 'review_pending',
    version_number: 1,
    content: { text: 'resumen' },
    confidence: 80,
    provider_name: 'mock-provider',
    model_name: 'mock-model',
    schema_version: 1,
    approved_by: null,
    approved_at: null,
    rejected_by: null,
    rejected_at: null,
    rejection_reason: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ai_disclaimer: 'Contenido generado mediante IA.',
    ...overrides,
  }
}

describe('ArtifactActions', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('muestra un aviso en vez de acciones cuando se visualiza una versión histórica', () => {
    render(
      <ArtifactActions
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={makeArtifact()}
        isViewingCurrentVersion={false}
        onChanged={vi.fn()}
      />,
    )
    expect(screen.getByText(/versión histórica/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /reject/i })).not.toBeInTheDocument()
  })

  it('un viewer no ve botones de acción', () => {
    const { container } = render(
      <ArtifactActions
        devUserId="u-viewer"
        role="viewer"
        currentUserId="u-viewer"
        professionalId="u-audiologist"
        artifact={makeArtifact()}
        isViewingCurrentVersion
        onChanged={vi.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('un audiologist no ve acciones sobre una sesión de otro profesional', () => {
    const { container } = render(
      <ArtifactActions
        devUserId="u-audiologist"
        role="audiologist"
        currentUserId="u-audiologist"
        professionalId="u-otro"
        artifact={makeArtifact()}
        isViewingCurrentVersion
        onChanged={vi.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('aprueba el artefacto vigente', async () => {
    const artifact = makeArtifact()
    fetchMock.mockResolvedValue(jsonResponse({ ...artifact, status: 'approved' }))
    const onChanged = vi.fn()
    const user = userEvent.setup()

    render(
      <ArtifactActions
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={artifact}
        isViewingCurrentVersion
        onChanged={onChanged}
      />,
    )

    await user.click(screen.getByRole('button', { name: /^approve$/i }))

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith({ ...artifact, status: 'approved' }))
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/ai-artifacts/artifact-1/approve'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('rechaza el artefacto con motivo opcional introducido en el prompt', async () => {
    const artifact = makeArtifact()
    fetchMock.mockResolvedValue(jsonResponse({ ...artifact, status: 'rejected' }))
    vi.spyOn(window, 'prompt').mockReturnValue('Falta contexto clínico')
    const onChanged = vi.fn()
    const user = userEvent.setup()

    render(
      <ArtifactActions
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={artifact}
        isViewingCurrentVersion
        onChanged={onChanged}
      />,
    )

    await user.click(screen.getByRole('button', { name: /^reject$/i }))

    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    const [, init] = fetchMock.mock.calls[0]
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      rejection_reason: 'Falta contexto clínico',
    })
  })

  it('no llama a la API si se cancela el prompt de rechazo', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue(null)
    const user = userEvent.setup()

    render(
      <ArtifactActions
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={makeArtifact()}
        isViewingCurrentVersion
        onChanged={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /^reject$/i }))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('muestra un error si la acción falla', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'internal_error', message: 'fallo' } }, { status: 500 }),
    )
    const user = userEvent.setup()

    render(
      <ArtifactActions
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={makeArtifact()}
        isViewingCurrentVersion
        onChanged={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /^approve$/i }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })
})
