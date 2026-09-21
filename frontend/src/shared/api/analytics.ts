import { apiRequest } from './client'
import type { ClinicAnalyticsSummary } from './types'

/** Único endpoint de `app/analytics/api/router.py` (Fase 15) —
 * `period_days` opcional (el backend usa 30 por defecto si se omite; ver
 * `DEFAULT_PERIOD_DAYS`), acotado a 1-365 igual que la API. */
export function getClinicAnalyticsSummary(
  devUserId: string,
  periodDays?: number,
): Promise<ClinicAnalyticsSummary> {
  const query = periodDays !== undefined ? `?period_days=${periodDays}` : ''
  return apiRequest<ClinicAnalyticsSummary>(`/api/v1/analytics/clinic-summary${query}`, {
    devUserId,
  })
}
