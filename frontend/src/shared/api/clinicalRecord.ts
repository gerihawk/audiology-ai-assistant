import { apiDownload, apiRequest } from './client'
import type { ClinicalRecordPage, ExportFormat } from './types'

export interface GetClinicalRecordParams {
  limit?: number
  offset?: number
}

export function getClinicalRecord(
  devUserId: string,
  patientId: string,
  params: GetClinicalRecordParams = {},
): Promise<ClinicalRecordPage> {
  const query = new URLSearchParams()
  query.set('limit', String(params.limit ?? 20))
  query.set('offset', String(params.offset ?? 0))
  return apiRequest<ClinicalRecordPage>(
    `/api/v1/patients/${patientId}/clinical-record?${query.toString()}`,
    { devUserId },
  )
}

export interface ExportClinicalRecordParams {
  /** Debe ser el `limit`/`offset` actualmente visible en la página cargada
   * (ver `ClinicalRecordPage.limit`/`.offset`) — la exportación usa la
   * misma ventana de sesiones que la vista, nunca un rango distinto ni
   * "todo el histórico" por omisión (`ClinicalRecordService.export_record`:
   * sin `limit` explícito, el backend asume el máximo exportable, no
   * "sin límite"). */
  limit: number
  offset: number
}

export function exportClinicalRecord(
  devUserId: string,
  patientId: string,
  format: ExportFormat,
  { limit, offset }: ExportClinicalRecordParams,
) {
  const query = new URLSearchParams({
    format,
    limit: String(limit),
    offset: String(offset),
  })
  return apiDownload(`/api/v1/patients/${patientId}/clinical-record/export?${query.toString()}`, {
    devUserId,
  })
}
