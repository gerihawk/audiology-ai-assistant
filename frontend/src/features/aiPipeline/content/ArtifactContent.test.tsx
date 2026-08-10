import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ArtifactContent } from './ArtifactContent'

describe('ArtifactContent', () => {
  it('transcript: muestra el texto y el idioma detectado', () => {
    render(
      <ArtifactContent
        artifactType="transcript"
        content={{ text: 'Buenos días, ¿en qué puedo ayudarle?', language: 'es' }}
        confidence={80}
      />,
    )
    expect(screen.getByText(/buenos días/i)).toBeInTheDocument()
    expect(screen.getByText(/es/i)).toBeInTheDocument()
  })

  it('summary: muestra el resumen como documento de lectura', () => {
    render(
      <ArtifactContent
        artifactType="summary"
        content={{ text: 'Paciente refiere dificultad auditiva progresiva.' }}
        confidence={75}
      />,
    )
    expect(screen.getByText(/dificultad auditiva progresiva/i)).toBeInTheDocument()
  })

  it('clinical_flags: renderiza cada señal como un ítem de lista con su explicación y confianza', () => {
    render(
      <ArtifactContent
        artifactType="clinical_flags"
        content={{
          flags: [
            {
              category: 'tinnitus_unilateral',
              description: 'Posible tinnitus unilateral referido por el paciente.',
              source_excerpt: 'me pita solo el oído derecho',
              ruleset_name: 'mock-ruleset',
            },
          ],
        }}
        confidence={55}
      />,
    )
    expect(screen.getByText('Tinnitus unilateral')).toBeInTheDocument()
    expect(screen.getByText(/posible tinnitus unilateral/i)).toBeInTheDocument()
    expect(screen.getByText(/me pita solo el oído derecho/i)).toBeInTheDocument()
    expect(screen.getByText(/55%/)).toBeInTheDocument()
  })

  it('clinical_flags: muestra un mensaje cuando no hay señales detectadas', () => {
    render(
      <ArtifactContent artifactType="clinical_flags" content={{ flags: [] }} confidence={80} />,
    )
    expect(screen.getByText(/no se han detectado señales de alerta/i)).toBeInTheDocument()
  })

  it('missing_information: se presenta como checklist no editable', () => {
    render(
      <ArtifactContent
        artifactType="missing_information"
        content={{
          items: [
            {
              topic: 'antecedentes_familiares',
              suggested_question: '¿Antecedentes familiares de pérdida auditiva?',
            },
          ],
        }}
        confidence={null}
      />,
    )
    const checkbox = screen.getByRole('checkbox', {
      name: /antecedentes familiares de pérdida auditiva/i,
    })
    expect(checkbox).toBeDisabled()
    expect(checkbox).not.toBeChecked()
  })

  it('anamnesis: transforma el JSON en una estructura legible, nunca JSON crudo', () => {
    render(
      <ArtifactContent
        artifactType="anamnesis"
        content={{
          motivo_consulta: {
            value: 'Dificultad para seguir conversaciones en grupo.',
            status: 'informado',
          },
          tinnitus: { value: '', status: 'no_preguntado' },
        }}
        confidence={70}
      />,
    )
    expect(screen.getByText('Motivo de consulta')).toBeInTheDocument()
    expect(screen.getByText(/dificultad para seguir conversaciones en grupo/i)).toBeInTheDocument()
    expect(screen.getByText('Informado')).toBeInTheDocument()
    expect(screen.getByText('Acúfenos (tinnitus)')).toBeInTheDocument()
    expect(screen.getByText('No preguntado')).toBeInTheDocument()
    expect(screen.queryByText(/{"/)).not.toBeInTheDocument()
  })
})
