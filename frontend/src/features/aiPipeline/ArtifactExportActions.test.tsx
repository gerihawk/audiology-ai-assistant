import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AIArtifact } from '../../shared/api/types'
import { ArtifactExportActions } from './ArtifactExportActions'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function binaryResponse(init: ResponseInit = {}) {
  return new Response(new Blob([new Uint8Array([1, 2, 3])]), {
    status: 200,
    headers: { 'content-type': 'application/pdf' },
    ...init,
  })
}

function makeArtifact(overrides: Partial<AIArtifact> = {}): AIArtifact {
  return {
    id: 'artifact-1',
    clinical_session_id: 's-1',
    artifact_type: 'summary',
    status: 'approved',
    version_number: 1,
    content: { text: 'x' },
    confidence: 80,
    provider_name: 'mock',
    model_name: 'mock-v1',
    schema_version: 1,
    approved_by: 'u-admin',
    approved_at: '2026-01-01T00:00:00Z',
    rejected_by: null,
    rejected_at: null,
    rejection_reason: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ai_disclaimer: 'Contenido generado mediante IA.',
    ruleset_disclaimer: null,
    ...overrides,
  }
}

describe('ArtifactExportActions', () => {
  const fetchMock = vi.fn()
  const originalCreateObjectURL = URL.createObjectURL
  const originalRevokeObjectURL = URL.revokeObjectURL

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    URL.createObjectURL = vi.fn(() => 'blob:mock-url')
    URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    URL.createObjectURL = originalCreateObjectURL
    URL.revokeObjectURL = originalRevokeObjectURL
  })

  it('no se ofrece exportación si el artefacto no está approved', () => {
    const { container } = render(
      <ArtifactExportActions
        devUserId="u-admin"
        role="admin"
        artifact={makeArtifact({ status: 'review_pending' })}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('un viewer nunca ve las acciones de exportación, aunque el artefacto esté approved', () => {
    const { container } = render(
      <ArtifactExportActions devUserId="u-viewer" role="viewer" artifact={makeArtifact()} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('admin/audiologist ven Exportar PDF y Exportar TXT sobre un artefacto approved', () => {
    render(<ArtifactExportActions devUserId="u-admin" role="admin" artifact={makeArtifact()} />)
    expect(screen.getByRole('button', { name: /exportar pdf/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /exportar txt/i })).toBeInTheDocument()
  })

  it('Exportar PDF llama al endpoint real con format=pdf y dispara la descarga', async () => {
    fetchMock.mockResolvedValue(
      binaryResponse({ headers: { 'content-disposition': 'attachment; filename="doc.pdf"' } }),
    )
    const user = userEvent.setup()
    render(<ArtifactExportActions devUserId="u-admin" role="admin" artifact={makeArtifact()} />)

    await user.click(screen.getByRole('button', { name: /exportar pdf/i }))

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/v1/ai-artifacts/artifact-1/export?format=pdf')
    expect(URL.createObjectURL).toHaveBeenCalled()
  })

  it('Exportar TXT llama al endpoint real con format=text', async () => {
    fetchMock.mockResolvedValue(
      binaryResponse({
        headers: {
          'content-type': 'text/plain; charset=utf-8',
          'content-disposition': 'attachment; filename="doc.txt"',
        },
      }),
    )
    const user = userEvent.setup()
    render(<ArtifactExportActions devUserId="u-admin" role="admin" artifact={makeArtifact()} />)

    await user.click(screen.getByRole('button', { name: /exportar txt/i }))

    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('format=text')
  })

  it('un 409 (artefacto sin versión aprobada vigente) se muestra con el mensaje real del backend', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: 'conflict',
            message:
              'El artefacto no tiene una versión aprobada y vigente disponible para exportar.',
          },
        },
        { status: 409 },
      ),
    )
    const user = userEvent.setup()
    render(<ArtifactExportActions devUserId="u-admin" role="admin" artifact={makeArtifact()} />)

    await user.click(screen.getByRole('button', { name: /exportar pdf/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/conflicto/i)
    expect(alert).toHaveTextContent(/no tiene una versión aprobada y vigente/i)
  })

  it('un 404 se muestra como "No encontrado"', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'not_found', message: 'Artefacto de IA no encontrado.' } },
        { status: 404 },
      ),
    )
    const user = userEvent.setup()
    render(<ArtifactExportActions devUserId="u-admin" role="admin" artifact={makeArtifact()} />)

    await user.click(screen.getByRole('button', { name: /exportar pdf/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/no encontrado/i)
  })
})
