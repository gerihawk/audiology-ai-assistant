import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AIArtifact, AIArtifactType, AIArtifactVersion } from '../../shared/api/types'
import { ArtifactEditForm } from './ArtifactEditForm'

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
    status: 'approved',
    version_number: 1,
    content: { text: 'texto original' },
    confidence: 80,
    provider_name: 'mock-provider',
    model_name: 'mock-model',
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

function makeVersion(overrides: Partial<AIArtifactVersion> = {}): AIArtifactVersion {
  return {
    id: 'v1',
    version_number: 1,
    content: { text: 'texto original' },
    confidence: 80,
    source: 'ai_generated',
    provider_name: 'mock-provider',
    model_name: 'mock-model',
    is_current: true,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('ArtifactEditForm', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('no se muestra si el rol no tiene permiso (viewer)', () => {
    const { container } = render(
      <ArtifactEditForm
        devUserId="u-viewer"
        role="viewer"
        currentUserId="u-viewer"
        professionalId="u-audiologist"
        artifact={makeArtifact()}
        currentVersion={makeVersion()}
        isViewingCurrentVersion
        onChanged={vi.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('un audiologist no ve el botón sobre una sesión de otro profesional', () => {
    const { container } = render(
      <ArtifactEditForm
        devUserId="u-audiologist"
        role="audiologist"
        currentUserId="u-audiologist"
        professionalId="u-otro"
        artifact={makeArtifact()}
        currentVersion={makeVersion()}
        isViewingCurrentVersion
        onChanged={vi.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('nunca se muestra sobre una versión histórica, aunque el resto de permisos lo permitan', () => {
    const { container } = render(
      <ArtifactEditForm
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={makeArtifact()}
        currentVersion={makeVersion({ is_current: false })}
        isViewingCurrentVersion={false}
        onChanged={vi.fn()}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it.each([
    'transcript',
    'clinical_flags',
    'missing_information',
    'anamnesis',
    'session_notes',
  ] as const)(
    'no ofrece edición estructurada todavía para %s (fuera de alcance de este bloque)',
    (artifactType: AIArtifactType) => {
      const { container } = render(
        <ArtifactEditForm
          devUserId="u-admin"
          role="admin"
          currentUserId="u-admin"
          professionalId="u-audiologist"
          artifact={makeArtifact({ artifact_type: artifactType })}
          currentVersion={makeVersion()}
          isViewingCurrentVersion
          onChanged={vi.fn()}
        />,
      )
      expect(container).toBeEmptyDOMElement()
    },
  )

  it('summary: precarga el texto vigente, guarda vía PATCH y entrega la respuesta real (nunca una mutación local)', async () => {
    const patchedArtifact = makeArtifact({
      status: 'review_pending',
      version_number: 2,
      approved_by: null,
      approved_at: null,
      content: { text: 'texto editado' },
    })
    fetchMock.mockResolvedValue(jsonResponse(patchedArtifact))
    const onChanged = vi.fn()
    const user = userEvent.setup()

    render(
      <ArtifactEditForm
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={makeArtifact()}
        currentVersion={makeVersion({ content: { text: 'texto original' } })}
        isViewingCurrentVersion
        onChanged={onChanged}
      />,
    )

    await user.click(screen.getByRole('button', { name: /editar contenido/i }))
    const textarea = screen.getByLabelText(/^contenido$/i) as HTMLTextAreaElement
    expect(textarea.value).toBe('texto original')

    await user.clear(textarea)
    await user.type(textarea, 'texto editado')
    await user.type(screen.getByLabelText(/nota de cambio/i), 'corrijo una errata')
    await user.click(screen.getByRole('button', { name: /guardar edición/i }))

    expect(onChanged).toHaveBeenCalledWith(patchedArtifact)
    // Nunca auto-aprobado: lo que se muestra tras guardar viene del backend
    // (review_pending, approved_by null), no de mutar el artifact original.
    expect(patchedArtifact.status).toBe('review_pending')
    expect(patchedArtifact.approved_by).toBeNull()

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/v1/ai-artifacts/artifact-1/content')
    expect(init).toMatchObject({ method: 'PATCH' })
    expect(JSON.parse(String(init.body))).toEqual({
      content: { text: 'texto editado' },
      change_note: 'corrijo una errata',
    })
  })

  it('patient_summary: mismo formulario que summary (mismo contrato {text})', () => {
    fetchMock.mockResolvedValue(jsonResponse(makeArtifact({ artifact_type: 'patient_summary' })))

    render(
      <ArtifactEditForm
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={makeArtifact({ artifact_type: 'patient_summary' })}
        currentVersion={makeVersion()}
        isViewingCurrentVersion
        onChanged={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /editar contenido/i })).toBeInTheDocument()
  })

  it('cancelar descarta los cambios sin llamar a la API', async () => {
    const user = userEvent.setup()
    render(
      <ArtifactEditForm
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={makeArtifact()}
        currentVersion={makeVersion()}
        isViewingCurrentVersion
        onChanged={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: /editar contenido/i }))
    await user.click(screen.getByRole('button', { name: /cancelar/i }))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /editar contenido/i })).toBeInTheDocument()
  })

  it('un 409 (versión desactualizada u otro conflicto) se muestra con el mensaje real del backend', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'conflict', message: 'El artefacto fue modificado por otra persona.' } },
        { status: 409 },
      ),
    )
    const user = userEvent.setup()

    render(
      <ArtifactEditForm
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        professionalId="u-audiologist"
        artifact={makeArtifact()}
        currentVersion={makeVersion()}
        isViewingCurrentVersion
        onChanged={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: /editar contenido/i }))
    await user.click(screen.getByRole('button', { name: /guardar edición/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/conflicto/i)
    expect(alert).toHaveTextContent('El artefacto fue modificado por otra persona.')
  })
})
