import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { PipelineStepOutcome } from '../../shared/api/types'
import { PipelineStepOutcomesList } from './PipelineStepOutcomesList'

function makeOutcome(overrides: Partial<PipelineStepOutcome> = {}): PipelineStepOutcome {
  return {
    artifact_type: 'transcript',
    status: 'completed',
    failure_reason: null,
    skipped_reason: null,
    latency_ms: 10,
    execution_time_ms: 10,
    input_token_count: null,
    output_token_count: null,
    estimated_cost_usd: null,
    ...overrides,
  }
}

describe('PipelineStepOutcomesList', () => {
  it('no renderiza nada si no hay step_outcomes', () => {
    const { container } = render(<PipelineStepOutcomesList stepOutcomes={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('muestra un paso completado sin motivo adicional', () => {
    render(
      <PipelineStepOutcomesList
        stepOutcomes={[makeOutcome({ artifact_type: 'transcript', status: 'completed' })]}
      />,
    )
    expect(screen.getByText('Transcripción')).toBeInTheDocument()
    expect(screen.getByText('Completado')).toBeInTheDocument()
  })

  it('muestra el motivo de un paso fallido (failure_reason)', () => {
    render(
      <PipelineStepOutcomesList
        stepOutcomes={[
          makeOutcome({
            artifact_type: 'summary',
            status: 'failed',
            failure_reason: 'El proveedor devolvió un error de red.',
          }),
        ]}
      />,
    )
    expect(screen.getByText('Fallido')).toBeInTheDocument()
    expect(screen.getByText(/el proveedor devolvió un error de red/i)).toBeInTheDocument()
  })

  it('muestra el motivo de un paso omitido (skipped_reason)', () => {
    render(
      <PipelineStepOutcomesList
        stepOutcomes={[
          makeOutcome({
            artifact_type: 'session_notes',
            status: 'skipped',
            skipped_reason: 'No existe anamnesis previa aprobada del paciente.',
          }),
        ]}
      />,
    )
    expect(screen.getByText('Notas de la sesión')).toBeInTheDocument()
    expect(screen.getByText('Omitido')).toBeInTheDocument()
    expect(screen.getByText(/no existe anamnesis previa aprobada/i)).toBeInTheDocument()
  })

  it('nunca inventa provider/model por step: el contrato real no los expone ahí', () => {
    render(
      <PipelineStepOutcomesList stepOutcomes={[makeOutcome({ artifact_type: 'transcript' })]} />,
    )
    expect(screen.queryByText(/mock-provider/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/proveedor/i)).not.toBeInTheDocument()
  })
})
