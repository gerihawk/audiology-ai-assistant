import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ClinicalRecordDocument, DevUser } from '../../shared/api/types'
import { ClinicalRecordDocumentCard } from './ClinicalRecordDocumentCard'

const PROFESSIONAL_OPTIONS: DevUser[] = [
  { id: 'u-audiologist', clinic_id: 'c-1', display_name: 'Dra. Ejemplo', role: 'audiologist' },
]

function makeDocument(overrides: Partial<ClinicalRecordDocument> = {}): ClinicalRecordDocument {
  return {
    ai_artifact_id: 'a-1',
    artifact_type: 'summary',
    version_number: 2,
    approved_by: 'u-audiologist',
    approved_at: '2026-01-05T10:00:00Z',
    content: { text: 'Resumen aprobado.' },
    is_current_baseline: false,
    ruleset_disclaimer: null,
    ...overrides,
  }
}

describe('ClinicalRecordDocumentCard', () => {
  it('reutiliza ArtifactContent: muestra tipo, versión y aprobado_por/aprobado_at sin fabricar un AIArtifact', () => {
    render(
      <ClinicalRecordDocumentCard
        document={makeDocument()}
        professionalOptions={PROFESSIONAL_OPTIONS}
      />,
    )
    expect(screen.getByText('Resumen')).toBeInTheDocument()
    expect(screen.getByText('Versión 2')).toBeInTheDocument()
    expect(screen.getByText(/aprobado por dra\. ejemplo/i)).toBeInTheDocument()
    expect(screen.getByText(/resumen aprobado\./i)).toBeInTheDocument()
  })

  it('anamnesis vigente: se marca inequívocamente como "Anamnesis vigente"', () => {
    render(
      <ClinicalRecordDocumentCard
        document={makeDocument({
          artifact_type: 'anamnesis',
          is_current_baseline: true,
          content: {},
        })}
        professionalOptions={PROFESSIONAL_OPTIONS}
      />,
    )
    expect(screen.getByText('Anamnesis vigente')).toBeInTheDocument()
    expect(screen.queryByText('Anamnesis histórica')).not.toBeInTheDocument()
  })

  it('anamnesis histórica (is_current_baseline=false): se marca inequívocamente como "Anamnesis histórica"', () => {
    render(
      <ClinicalRecordDocumentCard
        document={makeDocument({
          artifact_type: 'anamnesis',
          is_current_baseline: false,
          content: {},
        })}
        professionalOptions={PROFESSIONAL_OPTIONS}
      />,
    )
    expect(screen.getByText('Anamnesis histórica')).toBeInTheDocument()
    expect(screen.queryByText('Anamnesis vigente')).not.toBeInTheDocument()
  })

  it('el badge de baseline nunca aparece en tipos que no son anamnesis', () => {
    render(
      <ClinicalRecordDocumentCard
        document={makeDocument({ artifact_type: 'summary', is_current_baseline: false })}
        professionalOptions={PROFESSIONAL_OPTIONS}
      />,
    )
    expect(screen.queryByText(/anamnesis vigente/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/anamnesis histórica/i)).not.toBeInTheDocument()
  })

  it('clinical_flags muestra el RULESET_DISCLAIMER del documento longitudinal', () => {
    const disclaimer = 'Checklist de demostración. No validado clínicamente.'
    render(
      <ClinicalRecordDocumentCard
        document={makeDocument({
          artifact_type: 'clinical_flags',
          content: { flags: [] },
          ruleset_disclaimer: disclaimer,
        })}
        professionalOptions={PROFESSIONAL_OPTIONS}
      />,
    )
    expect(screen.getByRole('note')).toHaveTextContent(disclaimer)
  })

  it('no muestra confianza numérica inventada: el contrato longitudinal no la trae', () => {
    render(
      <ClinicalRecordDocumentCard
        document={makeDocument({
          artifact_type: 'clinical_flags',
          content: {
            flags: [
              {
                category: 'otalgia',
                description: 'x',
                source_excerpt: null,
                ruleset_name: 'demo',
              },
            ],
          },
        })}
        professionalOptions={PROFESSIONAL_OPTIONS}
      />,
    )
    expect(screen.getByText(/confianza: no disponible/i)).toBeInTheDocument()
  })
})
