import type { AIArtifactType } from '../../../shared/api/types'
import { AnamnesisContent } from './AnamnesisContent'
import { ClinicalFlagsContent } from './ClinicalFlagsContent'
import { MissingInformationContent } from './MissingInformationContent'
import { SummaryContent } from './SummaryContent'
import { TranscriptContent } from './TranscriptContent'

interface Props {
  artifactType: AIArtifactType
  content: Record<string, unknown>
  confidence: number | null
}

/** Traduce el `content` (JSON) de cada tipo de artefacto a una vista
 * legible — nunca se muestra JSON crudo al usuario. */
export function ArtifactContent({ artifactType, content, confidence }: Props) {
  switch (artifactType) {
    case 'transcript':
      return <TranscriptContent content={content} />
    case 'summary':
      return <SummaryContent content={content} />
    case 'clinical_flags':
      return <ClinicalFlagsContent content={content} confidence={confidence} />
    case 'missing_information':
      return <MissingInformationContent content={content} />
    case 'anamnesis':
      return <AnamnesisContent content={content} />
  }
}
