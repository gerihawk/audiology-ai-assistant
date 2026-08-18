import { useEffect, useState } from 'react'
import { listAIArtifactVersions } from '../../shared/api/aiPipeline'
import type { AIArtifact, AIArtifactVersion, Role } from '../../shared/api/types'
import { AIDisclaimer } from './AIDisclaimer'
import { ArtifactActions } from './ArtifactActions'
import { ArtifactEditForm } from './ArtifactEditForm'
import { ArtifactMetadata } from './ArtifactMetadata'
import { ArtifactVersionList } from './ArtifactVersionList'
import { ArtifactContent } from './content/ArtifactContent'
import { getArtifactTypeLabel } from './labels'

interface Props {
  devUserId: string
  role: Role | undefined
  currentUserId: string | undefined
  professionalId: string
  artifact: AIArtifact
  refreshToken: number
  onBack: () => void
  onChanged: (artifact: AIArtifact) => void
}

type VersionsState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; versions: AIArtifactVersion[] }

export function ArtifactViewer({
  devUserId,
  role,
  currentUserId,
  professionalId,
  artifact,
  refreshToken,
  onBack,
  onChanged,
}: Props) {
  const [state, setState] = useState<VersionsState>({ status: 'loading' })
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    listAIArtifactVersions(devUserId, artifact.id)
      .then((response) => {
        if (cancelled) return
        setState({ status: 'ready', versions: response.items })
        const current = response.items.find((v) => v.is_current) ?? response.items[0]
        setSelectedVersionId(current?.id ?? null)
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setState({
          status: 'error',
          message: error instanceof Error ? error.message : 'No se pudo cargar el historial.',
        })
      })
    return () => {
      cancelled = true
    }
  }, [devUserId, artifact.id, refreshToken])

  return (
    <div>
      <button type="button" onClick={onBack}>
        Volver al listado de artefactos
      </button>

      <h3>{getArtifactTypeLabel(artifact.artifact_type)}</h3>

      <AIDisclaimer text={artifact.ai_disclaimer} />

      {state.status === 'loading' && <p role="status">Cargando historial de versiones…</p>}
      {state.status === 'error' && (
        <p role="alert">Error al cargar el historial: {state.message}</p>
      )}

      {state.status === 'ready' &&
        (() => {
          const selectedVersion =
            state.versions.find((v) => v.id === selectedVersionId) ?? state.versions[0]
          if (!selectedVersion) {
            return <p>Este artefacto no tiene ninguna versión todavía.</p>
          }

          return (
            <>
              <ArtifactMetadata
                status={artifact.status}
                versionNumber={selectedVersion.version_number}
                isCurrentVersion={selectedVersion.is_current}
                confidence={selectedVersion.confidence}
                providerName={selectedVersion.provider_name}
                modelName={selectedVersion.model_name}
                createdAt={selectedVersion.created_at}
                approvedAt={selectedVersion.is_current ? artifact.approved_at : null}
                rejectedAt={selectedVersion.is_current ? artifact.rejected_at : null}
                rejectionReason={selectedVersion.is_current ? artifact.rejection_reason : null}
              />

              <ArtifactContent
                artifactType={artifact.artifact_type}
                content={selectedVersion.content}
                confidence={selectedVersion.confidence}
                rulesetDisclaimer={artifact.ruleset_disclaimer}
              />

              <ArtifactVersionList
                versions={state.versions}
                selectedVersionId={selectedVersion.id}
                onSelect={(version) => setSelectedVersionId(version.id)}
              />

              <ArtifactEditForm
                devUserId={devUserId}
                role={role}
                currentUserId={currentUserId}
                professionalId={professionalId}
                artifact={artifact}
                currentVersion={selectedVersion}
                isViewingCurrentVersion={selectedVersion.is_current}
                onChanged={onChanged}
              />

              <ArtifactActions
                devUserId={devUserId}
                role={role}
                currentUserId={currentUserId}
                professionalId={professionalId}
                artifact={artifact}
                isViewingCurrentVersion={selectedVersion.is_current}
                onChanged={onChanged}
              />
            </>
          )
        })()}
    </div>
  )
}
