import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AIArtifact, AIArtifactType } from '../../shared/api/types'
import { ArtifactList } from './ArtifactList'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function makeArtifact(
  artifactType: AIArtifactType,
  overrides: Partial<AIArtifact> = {},
): AIArtifact {
  return {
    id: `artifact-${artifactType}`,
    clinical_session_id: 's-1',
    artifact_type: artifactType,
    status: 'review_pending',
    version_number: 1,
    content: {},
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

describe('ArtifactList', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('muestra un estado de carga mientras llega la respuesta', () => {
    fetchMock.mockReturnValue(new Promise(() => {}))
    render(
      <ArtifactList
        devUserId="u-admin"
        clinicalSessionId="s-1"
        refreshToken={0}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent(/cargando/i)
  })

  it('muestra un mensaje de error si falla la carga', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'internal_error', message: 'fallo' } }, { status: 500 }),
    )
    render(
      <ArtifactList
        devUserId="u-admin"
        clinicalSessionId="s-1"
        refreshToken={0}
        onSelect={vi.fn()}
      />,
    )
    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('muestra un mensaje cuando no se ha ejecutado el pipeline todavía', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [] }))
    render(
      <ArtifactList
        devUserId="u-admin"
        clinicalSessionId="s-1"
        refreshToken={0}
        onSelect={vi.fn()}
      />,
    )
    expect(await screen.findByText(/todavía no se ha ejecutado el pipeline/i)).toBeInTheDocument()
  })

  it('lista los artefactos en el orden canónico del pipeline, no en el orden de la API', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        items: [
          makeArtifact('anamnesis'),
          makeArtifact('clinical_flags'),
          makeArtifact('missing_information'),
          makeArtifact('summary'),
          makeArtifact('transcript'),
        ],
      }),
    )
    render(
      <ArtifactList
        devUserId="u-admin"
        clinicalSessionId="s-1"
        refreshToken={0}
        onSelect={vi.fn()}
      />,
    )

    const items = await screen.findAllByRole('listitem')
    expect(items.map((item) => item.textContent)).toEqual([
      expect.stringContaining('Transcripción'),
      expect.stringContaining('Resumen'),
      expect.stringContaining('Señales de alerta'),
      expect.stringContaining('Información ausente'),
      expect.stringContaining('Anamnesis estructurada'),
    ])
  })

  it('abre el detalle del artefacto seleccionado', async () => {
    const artifact = makeArtifact('transcript')
    fetchMock.mockResolvedValue(jsonResponse({ items: [artifact] }))
    const onSelect = vi.fn()
    const user = userEvent.setup()

    render(
      <ArtifactList
        devUserId="u-admin"
        clinicalSessionId="s-1"
        refreshToken={0}
        onSelect={onSelect}
      />,
    )

    await user.click(await screen.findByRole('button', { name: /ver detalle/i }))
    expect(onSelect).toHaveBeenCalledWith(artifact)
  })

  it('vuelve a cargar cuando cambia refreshToken', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [] }))
    const { rerender } = render(
      <ArtifactList
        devUserId="u-admin"
        clinicalSessionId="s-1"
        refreshToken={0}
        onSelect={vi.fn()}
      />,
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    rerender(
      <ArtifactList
        devUserId="u-admin"
        clinicalSessionId="s-1"
        refreshToken={1}
        onSelect={vi.fn()}
      />,
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })
})
