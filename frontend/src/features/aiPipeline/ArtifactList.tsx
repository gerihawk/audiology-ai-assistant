import { useEffect, useState } from 'react'
import { listClinicalSessionArtifacts } from '../../shared/api/aiPipeline'
import type { AIArtifact } from '../../shared/api/types'
import { ArtifactCard } from './ArtifactCard'
import { getArtifactTypeOrder } from './labels'

interface Props {
  devUserId: string
  clinicalSessionId: string
  refreshToken: number
  onSelect: (artifact: AIArtifact) => void
}

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; items: AIArtifact[] }

export function ArtifactList({ devUserId, clinicalSessionId, refreshToken, onSelect }: Props) {
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  useEffect(() => {
    let cancelled = false
    setState({ status: 'loading' })
    listClinicalSessionArtifacts(devUserId, clinicalSessionId)
      .then((response) => {
        if (cancelled) return
        setState({ status: 'ready', items: response.items })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setState({
          status: 'error',
          message: error instanceof Error ? error.message : 'No se pudieron cargar los artefactos.',
        })
      })
    return () => {
      cancelled = true
    }
  }, [devUserId, clinicalSessionId, refreshToken])

  if (state.status === 'loading') {
    return <p role="status">Cargando artefactos de IA…</p>
  }

  if (state.status === 'error') {
    return <p role="alert">Error al cargar los artefactos: {state.message}</p>
  }

  if (state.items.length === 0) {
    return <p>Todavía no se ha ejecutado el pipeline de IA para esta sesión.</p>
  }

  const orderedItems = [...state.items].sort(
    (a, b) => getArtifactTypeOrder(a.artifact_type) - getArtifactTypeOrder(b.artifact_type),
  )

  return (
    <ul className="artifact-list" aria-label="Artefactos de IA de la sesión">
      {orderedItems.map((artifact) => (
        <ArtifactCard key={artifact.id} artifact={artifact} onSelect={onSelect} />
      ))}
    </ul>
  )
}
