import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClinicAnalyticsSummary } from '../../shared/api/types'
import { AnalyticsPanel } from './AnalyticsPanel'

function makeClinicSummary(
  overrides: Partial<ClinicAnalyticsSummary> = {},
): ClinicAnalyticsSummary {
  return {
    scope: 'clinic',
    period_days: 30,
    period_start: '2026-08-22T00:00:00Z',
    period_end: '2026-09-21T00:00:00Z',
    patients: { total: 5, new_in_period: 2 },
    sessions_total_in_period: 8,
    sessions_by_status: {
      scheduled: 1,
      in_progress: 1,
      completed: 4,
      review_pending: 1,
      reviewed: 1,
      cancelled: 0,
    },
    sessions_trend: [
      { day: '2026-09-19', count: 2 },
      { day: '2026-09-20', count: 3 },
    ],
    ai_billable_runs_in_period: 3,
    ai_artifacts_by_status: { review_pending: 1, approved: 2, rejected: 0 },
    professional_activity: [
      { professional_id: 'p-1', display_name: 'Ana Profesional', sessions_in_period: 5 },
      { professional_id: 'p-2', display_name: 'Bruno Profesional', sessions_in_period: 3 },
    ],
    ...overrides,
  }
}

function makeOwnSummary(overrides: Partial<ClinicAnalyticsSummary> = {}): ClinicAnalyticsSummary {
  return makeClinicSummary({
    scope: 'own',
    patients: null,
    professional_activity: null,
    ...overrides,
  })
}

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('AnalyticsPanel', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('no renderiza nada ni llama a la API para un viewer', () => {
    const { container } = render(<AnalyticsPanel devUserId="u-viewer" role="viewer" />)
    expect(container).toBeEmptyDOMElement()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('muestra el resumen de clínica completo para admin', async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeClinicSummary()))
    render(<AnalyticsPanel devUserId="u-admin" role="admin" />)

    const resumen = await screen.findByRole('region', { name: 'Resumen del periodo' })
    expect(within(resumen).getByText('5')).toBeInTheDocument()
    expect(within(resumen).getByText('2')).toBeInTheDocument()
    expect(within(resumen).getByText('8')).toBeInTheDocument()
    expect(within(resumen).getByText('3')).toBeInTheDocument()

    expect(screen.getByRole('region', { name: 'Actividad por profesional' })).toBeInTheDocument()

    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/analytics/clinic-summary')
    expect(String(url)).toContain('period_days=30')
  })

  it('para audiologist no muestra pacientes ni actividad por profesional', async () => {
    fetchMock.mockResolvedValue(jsonResponse(makeOwnSummary()))
    render(<AnalyticsPanel devUserId="u-audio" role="audiologist" />)

    await screen.findByRole('region', { name: 'Resumen del periodo' })
    expect(screen.queryByText('Pacientes totales')).not.toBeInTheDocument()
    expect(
      screen.queryByRole('region', { name: 'Actividad por profesional' }),
    ).not.toBeInTheDocument()
  })

  it('al cambiar el periodo, vuelve a pedir el resumen con el nuevo period_days', async () => {
    const user = userEvent.setup()
    fetchMock.mockResolvedValue(jsonResponse(makeClinicSummary()))
    render(<AnalyticsPanel devUserId="u-admin" role="admin" />)

    await screen.findByRole('region', { name: 'Resumen del periodo' })
    await user.click(screen.getByRole('button', { name: '90 días' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const [url] = fetchMock.mock.calls[1]
    expect(String(url)).toContain('period_days=90')
  })

  it('muestra el error del backend si falla la carga del resumen', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'forbidden', message: 'No autorizado.' } }, { status: 403 }),
    )
    render(<AnalyticsPanel devUserId="u-admin" role="admin" />)

    expect(await screen.findByText(/no autorizado/i)).toBeInTheDocument()
  })
})
