import type { AIArtifactVersion } from '../../shared/api/types'
import { formatDateTime } from './format'

interface Props {
  versions: AIArtifactVersion[]
  selectedVersionId: string
  onSelect: (version: AIArtifactVersion) => void
}

/** Lista de versiones, más reciente primero. La versión vigente se marca
 * explícitamente ("vigente"); la seleccionada actualmente en pantalla se
 * distingue con `aria-current`. Permite navegar el historial completo sin
 * perder de vista cuál es la versión activa del artefacto. */
export function ArtifactVersionList({ versions, selectedVersionId, onSelect }: Props) {
  if (versions.length <= 1) {
    return <p>Todavía no hay más de una versión de este artefacto.</p>
  }

  return (
    <ul className="artifact-version-list" aria-label="Historial de versiones">
      {versions.map((version) => (
        <li key={version.id}>
          <button
            type="button"
            aria-current={version.id === selectedVersionId ? 'true' : undefined}
            onClick={() => onSelect(version)}
          >
            Versión {version.version_number}
            {version.is_current ? ' (vigente)' : ''} — {formatDateTime(version.created_at)}
          </button>
        </li>
      ))}
    </ul>
  )
}
