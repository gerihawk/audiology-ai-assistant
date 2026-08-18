import { useState } from 'react'
import { exportAIArtifact } from '../../shared/api/aiPipeline'
import type { AIArtifact, ExportFormat, Role } from '../../shared/api/types'
import { canExportClinicalDocument } from '../../shared/clinicalDocumentPermissions'
import { downloadFile } from '../../shared/downloadFile'
import { describeActionError } from '../../shared/apiErrorMessage'

interface Props {
  devUserId: string
  role: Role | undefined
  artifact: AIArtifact
}

const FALLBACK_EXTENSION: Record<ExportFormat, string> = { pdf: 'pdf', text: 'txt' }

/** `GET /ai-artifacts/{id}/export` — ver `ExportService.export()`. Nunca
 * se dispara automáticamente tras aprobar: siempre es una acción explícita
 * del profesional. */
export function ArtifactExportActions({ devUserId, role, artifact }: Props) {
  const [busyFormat, setBusyFormat] = useState<ExportFormat | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (artifact.status !== 'approved') return null
  if (!canExportClinicalDocument(role)) return null

  async function handleExport(format: ExportFormat) {
    if (busyFormat) return
    setBusyFormat(format)
    setError(null)
    try {
      const { blob, filename } = await exportAIArtifact(devUserId, artifact.id, format)
      // El nombre siempre lo decide el backend (Content-Disposition); el
      // fallback solo cubre el caso, hoy anómalo, de que no llegue.
      downloadFile(blob, filename ?? `documento-clinico.${FALLBACK_EXTENSION[format]}`)
    } catch (err) {
      const described = describeActionError(err)
      setError(`${described.label}: ${described.message}`)
    } finally {
      setBusyFormat(null)
    }
  }

  return (
    <div className="artifact-export-actions">
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
