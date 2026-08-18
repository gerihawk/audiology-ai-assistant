import { useState } from 'react'
import { exportClinicalRecord } from '../../shared/api/clinicalRecord'
import type { ExportFormat, Role } from '../../shared/api/types'
import { describeActionError } from '../../shared/apiErrorMessage'
import { canExportClinicalDocument } from '../../shared/clinicalDocumentPermissions'
import { downloadFile } from '../../shared/downloadFile'

interface Props {
  devUserId: string
  role: Role | undefined
  patientId: string
  /** El limit/offset actualmente visible en la página cargada — la
   * exportación usa exactamente esta ventana, nunca "todo el histórico"
   * (ver `ClinicalRecordService.export_record`: sin `limit` explícito el
   * backend asume el máximo exportable, no "sin límite"). */
  limit: number
  offset: number
}

const FALLBACK_EXTENSION: Record<ExportFormat, string> = { pdf: 'pdf', text: 'txt' }

/** `GET /patients/{id}/clinical-record/export` — ver
 * `ClinicalRecordService.export_record()`. `viewer` nunca ve estos
 * botones (`ClinicalDocumentAction.EXPORT`, sin ownership) aunque sí puede
 * leer la historia clínica — asimetría real del backend, reflejada aquí. */
export function ClinicalRecordExportActions({ devUserId, role, patientId, limit, offset }: Props) {
  const [busyFormat, setBusyFormat] = useState<ExportFormat | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (!canExportClinicalDocument(role)) return null

  async function handleExport(format: ExportFormat) {
    if (busyFormat) return
    setBusyFormat(format)
    setError(null)
    try {
      const { blob, filename } = await exportClinicalRecord(devUserId, patientId, format, {
        limit,
        offset,
      })
      downloadFile(blob, filename ?? `historia-clinica.${FALLBACK_EXTENSION[format]}`)
    } catch (err) {
      // Nunca se convierte en "error genérico": el 409 por
      // `clinical_record_export_max_sessions` ya trae su propio mensaje
      // ("use limit/offset para segmentar la exportación") — se muestra
      // tal cual, sin reinterpretarlo ni truncar limit por nuestra cuenta.
      const described = describeActionError(err)
      setError(`${described.label}: ${described.message}`)
    } finally {
      setBusyFormat(null)
    }
  }

  return (
    <div className="clinical-record-export-actions">
      {error && <p role="alert">{error}</p>}
      <button type="button" disabled={busyFormat !== null} onClick={() => handleExport('pdf')}>
        {busyFormat === 'pdf' ? 'Exportando…' : 'Exportar PDF'}
      </button>
      <button type="button" disabled={busyFormat !== null} onClick={() => handleExport('text')}>
        {busyFormat === 'text' ? 'Exportando…' : 'Exportar TXT'}
      </button>
    </div>
  )
}
