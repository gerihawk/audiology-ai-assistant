import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AIArtifact, AIArtifactVersion } from '../../shared/api/types'
import { ArtifactViewer } from './ArtifactViewer'

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
    version_number: 2,
    content: { text: 'resumen vigente' },
    confidence: 80,
    provider_name: 'mock-provider',
    model_name: 'mock-model',
    schema_version: 1,
    approved_by: null,
    approved_at: null,
    rejected_by: null,
    rejected_at: null,
    rejection_reason: null,
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
    ai_disclaimer:
      'Contenido generado mediante IA. Debe ser revisado y aprobado por un profesional cualificado antes de incorporarse al expediente.',
    ruleset_disclaimer: null,
    ...overrides,
  }
}

function makeVersion(overrides: Partial<AIArtifactVersion> = {}): AIArtifactVersion {
  return {
    id: 'v1',
    version_number: 1,
    content: { text: 'resumen versión 1' },
    confidence: 40,
    source: 'ai_generated',
    provider_name: 'mock-provider',
    model_name: 'mock-model',
    is_current: false,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('ArtifactViewer', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('muestra el aviso legal obligatorio de IA con el texto devuelto por la API', async () => {
    const artifact = makeArtifact()
    fetchMock.mockResolvedValue(
      jsonResponse({ items: [makeVersion({ id: 'v2', version_number: 2, is_current: true })] }),
    )
    render(
      <ArtifactViewer
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={artifact}
        refreshToken={0}
        onBack={vi.fn()}
        onChanged={vi.fn()}
      />,
    )

    expect(await screen.findByRole('note')).toHaveTextContent(artifact.ai_disclaimer)
  })

  it('muestra un error si falla la carga del historial de versiones', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'internal_error', message: 'fallo' } }, { status: 500 }),
    )
    render(
      <ArtifactViewer
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={makeArtifact()}
        refreshToken={0}
        onBack={vi.fn()}
        onChanged={vi.fn()}
      />,
    )
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('selecciona la versión vigente por defecto y permite cambiar a una histórica', async () => {
    const artifact = makeArtifact()
    const current = makeVersion({
      id: 'v2',
      version_number: 2,
      is_current: true,
      content: { text: 'resumen versión 2' },
      confidence: 80,
    })
    const historical = makeVersion({ id: 'v1', version_number: 1, is_current: false })
    fetchMock.mockResolvedValue(jsonResponse({ items: [current, historical] }))
    const user = userEvent.setup()

    render(
      <ArtifactViewer
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={artifact}
        refreshToken={0}
        onBack={vi.fn()}
        onChanged={vi.fn()}
      />,
    )

    expect(await screen.findByText('resumen versión 2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^approve$/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /versión 1/i }))

    expect(await screen.findByText('resumen versión 1')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument()
    expect(screen.getByText(/versión histórica/i)).toBeInTheDocument()
  })

  it('vuelve a cargar el historial cuando cambia refreshToken (reejecución del pipeline)', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ items: [makeVersion({ id: 'v1', is_current: true })] }),
    )
    const { rerender } = render(
      <ArtifactViewer
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={makeArtifact()}
        refreshToken={0}
        onBack={vi.fn()}
        onChanged={vi.fn()}
      />,
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    rerender(
      <ArtifactViewer
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={makeArtifact()}
        refreshToken={1}
        onBack={vi.fn()}
        onChanged={vi.fn()}
      />,
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })

  it('llama a onBack al pulsar volver al listado', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [makeVersion({ is_current: true })] }))
    const onBack = vi.fn()
    const user = userEvent.setup()

    render(
      <ArtifactViewer
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={makeArtifact()}
        refreshToken={0}
        onBack={onBack}
        onChanged={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /volver al listado de artefactos/i }))
    expect(onBack).toHaveBeenCalled()
  })
})
