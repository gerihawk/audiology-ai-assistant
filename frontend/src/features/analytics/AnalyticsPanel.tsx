import { useCallback, useEffect, useState } from 'react'
import { getClinicAnalyticsSummary } from '../../shared/api/analytics'
import { describeActionError } from '../../shared/apiErrorMessage'
import type { ClinicAnalyticsSummary, Role } from '../../shared/api/types'
import { ARTIFACT_STATUS_LABELS } from '../aiPipeline/labels'
import { STATUS_LABELS, STATUSES } from '../clinicalSessions/labels'
import { STATUS_COLORS } from './chartTheme'
import { HorizontalBarChart } from './HorizontalBarChart'
import { canViewAnalytics } from './permissions'
import { SessionsTrendChart } from './SessionsTrendChart'
import { StatTile } from './StatTile'

type LoadState = 'loading' | 'ready' | 'error'

interface Props {
  devUserId: string
  role: Role | undefined
}

/** Presets del selector de periodo — "una fila con presets antes de un
 * rango personalizado" (ver interaction.md del skill de dataviz); no hay
 * rango personalizado en esta primera versión, los tres presets cubren el
 * caso de uso real de Gerard. 30 coincide con `DEFAULT_PERIOD_DAYS` del
 * backend. */
const PERIOD_PRESETS = [
  { days: 7, label: '7 días' },
  { days: 30, label: '30 días' },
  { days: 90, label: '90 días' },
]

/** Apartado "Analítica" (Fase 15) — resumen agregado de la clínica para
 * `admin`, o de la propia actividad para `audiologist` (ver
 * `AnalyticsService.get_summary` en el backend, `summary.scope`). Recibe
 * `devUserId`/`role` por props en vez de leer `useDevUser()` directamente
 * — mismo patrón que `BillingPanel`. */
export function AnalyticsPanel({ devUserId, role }: Props) {
  const [periodDays, setPeriodDays] = useState(30)
  const [summary, setSummary] = useState<ClinicAnalyticsSummary | null>(null)
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const canView = canViewAnalytics(role)

  const load = useCallback(() => {
    setLoadState('loading')
    setErrorMessage(null)
    getClinicAnalyticsSummary(devUserId, periodDays)
      .then((response) => {
        setSummary(response)
        setLoadState('ready')
      })
      .catch((error: unknown) => {
        const described = describeActionError(error)
        setErrorMessage(`${described.label}: ${described.message}`)
        setLoadState('error')
      })
  }, [devUserId, periodDays])

  useEffect(() => {
    if (canView) load()
  }, [canView, load])

  if (!canView) return null

  const statusItems = STATUSES.map((status) => ({
    label: STATUS_LABELS[status],
    value: summary?.sessions_by_status[status] ?? 0,
  }))

  const professionalActivityItems =
    summary?.professional_activity?.map((entry) => ({
      label: entry.display_name,
      value: entry.sessions_in_period,
    })) ?? []

  return (
    <div>
      <h2>Analítica</h2>

      <div role="group" aria-label="Periodo" className="analytics-period-selector">
        {PERIOD_PRESETS.map((preset) => (
          <button
            key={preset.days}
            type="button"
            aria-pressed={periodDays === preset.days}
            disabled={loadState === 'loading' && periodDays === preset.days}
            onClick={() => setPeriodDays(preset.days)}
          >
            {preset.label}
          </button>
        ))}
      </div>

      {errorMessage && <p role="alert">{errorMessage}</p>}

      {loadState === 'loading' && !summary && <p role="status">Cargando analítica…</p>}

      {summary && (
        <>
          <section aria-label="Resumen del periodo" className="analytics-kpi-row">
            {summary.patients && (
              <>
                <StatTile label="Pacientes totales" value={summary.patients.total} />
                <StatTile
                  label="Pacientes nuevos en el periodo"
                  value={summary.patients.new_in_period}
                />
              </>
            )}
            <StatTile label="Sesiones en el periodo" value={summary.sessions_total_in_period} />
            <StatTile
              label="Ejecuciones de IA facturables"
              value={summary.ai_billable_runs_in_period}
            />
          </section>

          <section aria-label="Tendencia de sesiones">
            <h3>Sesiones por día</h3>
            <SessionsTrendChart data={summary.sessions_trend} />
          </section>

          <section aria-label="Sesiones por estado">
            <h3>Sesiones por estado</h3>
            <HorizontalBarChart
              items={statusItems}
              emptyMessage="No hay sesiones registradas en este periodo."
            />
          </section>

          <section aria-label="Artefactos de IA por estado" className="analytics-kpi-row">
            <StatTile
              label={ARTIFACT_STATUS_LABELS.approved}
              value={summary.ai_artifacts_by_status.approved}
              accentColor={STATUS_COLORS.good}
            />
            <StatTile
              label={ARTIFACT_STATUS_LABELS.review_pending}
              value={summary.ai_artifacts_by_status.review_pending}
              accentColor={STATUS_COLORS.warning}
            />
            <StatTile
              label={ARTIFACT_STATUS_LABELS.rejected}
              value={summary.ai_artifacts_by_status.rejected}
              accentColor={STATUS_COLORS.critical}
            />
          </section>

          {summary.professional_activity && (
            <section aria-label="Actividad por profesional">
              <h3>Actividad por profesional</h3>
              <HorizontalBarChart
                items={professionalActivityItems}
                emptyMessage="Ningún profesional ha registrado sesiones en este periodo."
              />
            </section>
          )}
        </>
      )}
    </div>
  )
}
