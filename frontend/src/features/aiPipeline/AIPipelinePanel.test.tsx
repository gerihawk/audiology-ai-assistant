import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AIArtifact, AIArtifactType, AIArtifactVersion } from '../../shared/api/types'
import { AIPipelinePanel } from './AIPipelinePanel'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

/** Restringe la búsqueda de artefactos a la lista de artefactos, nunca a
 * cualquier `role="listitem"` de la pantalla — el panel también renderiza
 * el detalle de `step_outcomes` como lista, con sus propios `listitem`. */
async function findArtifactListItems() {
  const list = await screen.findByRole('list', { name: /artefactos de ia de la sesión/i })
  return within(list).getAllByRole('listitem')
}

const ARTIFACT_TYPES: AIArtifactType[] = [
  'transcript',
  'summary',
  'patient_summary',
  'clinical_flags',
  'missing_information',
  'anamnesis',
  'session_notes',
]

const DISCLAIMER =
  'Contenido generado mediante IA. Debe ser revisado y aprobado por un profesional cualificado antes de incorporarse al expediente.'
const RULESET_DISCLAIMER = 'Checklist de demostración. No validado clínicamente.'

/** Simula el backend real lo suficiente para probar la orquestación de
 * AIPipelinePanel de extremo a extremo: ejecutar el pipeline, listar,
 * abrir detalle, aprobar/rechazar, reejecutar y generar una nueva versión,
 * y cambiar entre versiones. */
function createBackendMock() {
  const artifacts = new Map<AIArtifactType, AIArtifact>()
  const versions = new Map<string, AIArtifactVersion[]>()

  function runPipeline(): AIArtifact[] {
    const result: AIArtifact[] = []
    for (const artifactType of ARTIFACT_TYPES) {
      const existing = artifacts.get(artifactType)
      const nextVersionNumber = existing ? (existing.version_number ?? 0) + 1 : 1
      const id = existing?.id ?? `artifact-${artifactType}`

      if (existing) {
        const previousVersions = versions.get(id) ?? []
        versions.set(
          id,
          previousVersions.map((v) => ({ ...v, is_current: false })),
        )
      }

      const artifact: AIArtifact = {
        id,
        clinical_session_id: 's-1',
        artifact_type: artifactType,
        status: 'review_pending',
        version_number: nextVersionNumber,
        content: { text: `${artifactType} v${nextVersionNumber}`, flags: [], items: [] },
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
        ai_disclaimer: DISCLAIMER,
        ruleset_disclaimer: artifactType === 'clinical_flags' ? RULESET_DISCLAIMER : null,
        ...(existing ? { id: existing.id } : {}),
      }
      artifacts.set(artifactType, artifact)

      const version: AIArtifactVersion = {
        id: `${id}-v${nextVersionNumber}`,
        version_number: nextVersionNumber,
        content: artifact.content as Record<string, unknown>,
        confidence: artifact.confidence,
        source: 'ai_generated',
        provider_name: artifact.provider_name,
        model_name: artifact.model_name,
        is_current: true,
        created_at: '2026-01-01T00:00:00Z',
      }
      versions.set(id, [...(versions.get(id) ?? []), version])
      result.push(artifact)
    }
    return result
  }

  function findById(artifactId: string): AIArtifact | undefined {
    return [...artifacts.values()].find((a) => a.id === artifactId)
  }

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'

    if (method === 'POST' && url.includes('/run-mock-pipeline')) {
      const items = runPipeline()
      return jsonResponse({
        pipeline_run_id: 'run-1',
        status: 'completed',
        started_at: '2026-01-01T00:00:00Z',
        completed_at: '2026-01-01T00:00:05Z',
        artifacts: items,
        step_outcomes: items.map((a) => ({
          artifact_type: a.artifact_type,
          status: 'completed',
          failure_reason: null,
          skipped_reason: null,
          latency_ms: 10,
          execution_time_ms: 10,
          input_token_count: null,
          output_token_count: null,
          estimated_cost_usd: null,
        })),
      })
    }

    if (method === 'GET' && url.includes('/artifacts')) {
      return jsonResponse({ items: [...artifacts.values()] })
    }

    const versionsMatch = url.match(/ai-artifacts\/([^/]+)\/versions/)
    if (method === 'GET' && versionsMatch) {
      return jsonResponse({ items: versions.get(versionsMatch[1]) ?? [] })
    }

    const approveMatch = url.match(/ai-artifacts\/([^/]+)\/approve/)
    if (method === 'POST' && approveMatch) {
      const artifact = findById(approveMatch[1])
      if (!artifact) return jsonResponse({}, { status: 404 })
      const updated = {
        ...artifact,
        status: 'approved' as const,
        approved_at: '2026-01-01T00:00:00Z',
      }
      artifacts.set(artifact.artifact_type, updated)
      return jsonResponse(updated)
    }

    const rejectMatch = url.match(/ai-artifacts\/([^/]+)\/reject/)
    if (method === 'POST' && rejectMatch) {
      const artifact = findById(rejectMatch[1])
      if (!artifact) return jsonResponse({}, { status: 404 })
      const body = init?.body ? JSON.parse(String(init.body)) : {}
      const updated = {
        ...artifact,
        status: 'rejected' as const,
        rejected_at: '2026-01-01T00:00:00Z',
        rejection_reason: body.rejection_reason ?? null,
      }
      artifacts.set(artifact.artifact_type, updated)
      return jsonResponse(updated)
    }

    throw new Error(`Unhandled request in test mock: ${method} ${url}`)
  })

  return fetchMock
}

describe('AIPipelinePanel (integración)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('cubre el flujo completo: ejecutar, listar, aprobar, rechazar, reejecutar y cambiar de versión', async () => {
    const fetchMock = createBackendMock()
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()

    render(
      <AIPipelinePanel
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        clinicalSessionId="s-1"
        professionalId="u-audiologist"
      />,
    )

    expect(await screen.findByText(/todavía no se ha ejecutado el pipeline/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /run mock pipeline/i }))

    expect(await screen.findByRole('status')).toHaveTextContent(/7\/7 artefactos generados/i)
    const artifactItems = await findArtifactListItems()
    expect(artifactItems).toHaveLength(7)
    // Objetivo 3 de la auditoría: ninguno de los 7 tipos puede quedar con
    // una tarjeta sin etiqueta (antes ocurría con patient_summary/session_notes).
    for (const item of artifactItems) {
      expect(item.querySelector('strong')?.textContent?.trim()).toBeTruthy()
    }

    const patientSummaryItem = artifactItems.find((item) =>
      item.textContent?.includes('Resumen para el paciente'),
    )!
    await user.click(within(patientSummaryItem).getByRole('button', { name: /ver detalle/i }))
    expect(await screen.findByText('patient_summary v1')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /volver al listado de artefactos/i }))

    // ArtifactList se desmonta/remonta al volver — hay que volver a
    // consultar el DOM, las referencias de `artifactItems` ya no viven aquí.
    const itemsAfterPatientSummary = await findArtifactListItems()
    const sessionNotesItem = itemsAfterPatientSummary.find((item) =>
      item.textContent?.includes('Notas de la sesión'),
    )!
    await user.click(within(sessionNotesItem).getByRole('button', { name: /ver detalle/i }))
    // El mock de este test no puebla los 4 bloques reales, pero el viewer
    // debe seguir mostrando los 4 encabezados de bloque, nunca un hueco vacío.
    expect(await screen.findByText('Cambios desde la última visita')).toBeInTheDocument()
    expect(screen.getByText('Ajustes del dispositivo')).toBeInTheDocument()
    expect(screen.getByText('Molestias referidas por el paciente')).toBeInTheDocument()
    expect(screen.getByText('Próximos pasos')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /volver al listado de artefactos/i }))

    const itemsAfterSessionNotes = await findArtifactListItems()
    const summaryItem = itemsAfterSessionNotes.find(
      (item) => item.textContent?.includes('Resumen') && !item.textContent?.includes('paciente'),
    )!
    await user.click(within(summaryItem).getByRole('button', { name: /ver detalle/i }))

    expect(await screen.findByRole('note')).toHaveTextContent(DISCLAIMER)
    expect(screen.getByText('summary v1')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^approve$/i }))
    expect(await screen.findByText('Aprobado')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /volver al listado de artefactos/i }))

    const refreshedItems = await findArtifactListItems()
    const transcriptItem = refreshedItems.find((item) =>
      item.textContent?.includes('Transcripción'),
    )!
    await user.click(within(transcriptItem).getByRole('button', { name: /ver detalle/i }))

    await screen.findByText('transcript v1')
    vi.spyOn(window, 'prompt').mockReturnValue('Transcripción incompleta')
    await user.click(screen.getByRole('button', { name: /^reject$/i }))
    expect(await screen.findByText('Rechazado')).toBeInTheDocument()
    expect(screen.getByText(/transcripción incompleta/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /volver al listado de artefactos/i }))
    await user.click(screen.getByRole('button', { name: /run mock pipeline/i }))
    expect(await screen.findByRole('status')).toHaveTextContent(/7\/7 artefactos generados/i)

    const rerunItems = await findArtifactListItems()
    const transcriptAgain = rerunItems.find((item) => item.textContent?.includes('Transcripción'))!
    await user.click(within(transcriptAgain).getByRole('button', { name: /ver detalle/i }))

    expect(await screen.findByText('transcript v2')).toBeInTheDocument()
    expect(screen.getByText(/pendiente de revisión/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /versión 1/i }))
    expect(await screen.findByText('transcript v1')).toBeInTheDocument()
    expect(screen.getByText(/versión histórica/i)).toBeInTheDocument()
  })

  it('un viewer puede navegar todo el flujo de lectura pero nunca ve acciones de ejecución o disposición', async () => {
    const fetchMock = createBackendMock()
    vi.stubGlobal('fetch', fetchMock)
    // Pre-carga artefactos ejecutando el pipeline "de fondo" antes de renderizar como viewer.
    await fetchMock('http://test/api/v1/clinical-sessions/s-1/run-mock-pipeline', {
      method: 'POST',
    })
    const user = userEvent.setup()

    render(
      <AIPipelinePanel
        devUserId="u-viewer"
        role="viewer"
        currentUserId="u-viewer"
        clinicalSessionId="s-1"
        professionalId="u-audiologist"
      />,
    )

    expect(screen.queryByRole('button', { name: /run mock pipeline/i })).not.toBeInTheDocument()

    const items = await findArtifactListItems()
    const summaryItem = items.find(
      (item) => item.textContent?.includes('Resumen') && !item.textContent?.includes('paciente'),
    )!
    await user.click(within(summaryItem).getByRole('button', { name: /ver detalle/i }))

    expect(await screen.findByRole('note')).toHaveTextContent(DISCLAIMER)
    expect(screen.queryByRole('button', { name: /^approve$/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^reject$/i })).not.toBeInTheDocument()
  })
})
