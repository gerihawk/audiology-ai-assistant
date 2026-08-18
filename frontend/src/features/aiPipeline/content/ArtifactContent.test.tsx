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
        rulesetDisclaimer={null}
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
        rulesetDisclaimer={null}
      />,
    )
    expect(screen.getByText(/dificultad auditiva progresiva/i)).toBeInTheDocument()
  })

  it('patient_summary: mismo contrato que summary ({text}), reutiliza el mismo componente', () => {
    render(
      <ArtifactContent
        artifactType="patient_summary"
        content={{ text: 'Explicación en lenguaje llano para el paciente.' }}
        confidence={70}
        rulesetDisclaimer={null}
      />,
    )
    expect(screen.getByText(/explicación en lenguaje llano para el paciente/i)).toBeInTheDocument()
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
        rulesetDisclaimer={null}
      />,
    )
    expect(screen.getByText('Tinnitus unilateral')).toBeInTheDocument()
    expect(screen.getByText(/posible tinnitus unilateral/i)).toBeInTheDocument()
    expect(screen.getByText(/me pita solo el oído derecho/i)).toBeInTheDocument()
    expect(screen.getByText(/55%/)).toBeInTheDocument()
  })

  it('clinical_flags: muestra un mensaje cuando no hay señales detectadas', () => {
    render(
      <ArtifactContent
        artifactType="clinical_flags"
        content={{ flags: [] }}
        confidence={80}
        rulesetDisclaimer={null}
      />,
    )
    expect(screen.getByText(/no se han detectado señales de alerta/i)).toBeInTheDocument()
  })

  it('clinical_flags: muestra el RULESET_DISCLAIMER cuando la API lo envía', () => {
    const disclaimer = 'Checklist de demostración. No validado clínicamente.'
    render(
      <ArtifactContent
        artifactType="clinical_flags"
        content={{ flags: [] }}
        confidence={80}
        rulesetDisclaimer={disclaimer}
      />,
    )
    expect(screen.getByRole('note')).toHaveTextContent(disclaimer)
  })

  it('clinical_flags: no muestra ningún aviso de ruleset si la API envía null', () => {
    render(
      <ArtifactContent
        artifactType="clinical_flags"
        content={{ flags: [] }}
        confidence={80}
        rulesetDisclaimer={null}
      />,
    )
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
  })

  it.each([
    'transcript',
    'summary',
    'patient_summary',
    'missing_information',
    'anamnesis',
  ] as const)(
    '%s: el RULESET_DISCLAIMER de otro artefacto nunca se filtra a este tipo',
    (artifactType) => {
      const disclaimer = 'Checklist de demostración. No validado clínicamente.'
      render(
        <ArtifactContent
          artifactType={artifactType}
          content={{ text: 'x', items: [], flags: [] }}
          confidence={null}
          rulesetDisclaimer={disclaimer}
        />,
      )
      expect(screen.queryByText(disclaimer)).not.toBeInTheDocument()
    },
  )

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
        rulesetDisclaimer={null}
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
        rulesetDisclaimer={null}
      />,
    )
    expect(screen.getByText('Motivo de consulta')).toBeInTheDocument()
    expect(screen.getByText(/dificultad para seguir conversaciones en grupo/i)).toBeInTheDocument()
    expect(screen.getByText('Informado')).toBeInTheDocument()
    expect(screen.getByText('Acúfenos (tinnitus)')).toBeInTheDocument()
    expect(screen.getByText('No preguntado')).toBeInTheDocument()
    expect(screen.queryByText(/{"/)).not.toBeInTheDocument()
  })

  it('session_notes: renderiza los 4 bloques, con texto cuando hay contenido', () => {
    render(
      <ArtifactContent
        artifactType="session_notes"
        content={{
          changes_since_last_visit: {
            text: 'El paciente refiere mejoría desde la última visita.',
            source_excerpt: 'ha mejorado bastante',
          },
          device_adjustments: {
            text: 'Se ajustó el volumen del audífono durante la sesión.',
            source_excerpt: 'ajustamos el volumen',
          },
          patient_reported_issues: { text: '', source_excerpt: null },
          next_steps: { text: '', source_excerpt: null },
        }}
        confidence={55}
        rulesetDisclaimer={null}
      />,
    )
    expect(screen.getByText('Cambios desde la última visita')).toBeInTheDocument()
    expect(screen.getByText(/refiere mejoría desde la última visita/i)).toBeInTheDocument()
    expect(screen.getByText(/ha mejorado bastante/i)).toBeInTheDocument()
    expect(screen.getByText('Ajustes del dispositivo')).toBeInTheDocument()
    expect(screen.getByText(/se ajustó el volumen/i)).toBeInTheDocument()
  })

  it('session_notes: un bloque sin contenido se marca explícitamente, nunca se omite ni se inventa continuidad', () => {
    render(
      <ArtifactContent
        artifactType="session_notes"
        content={{
          changes_since_last_visit: { text: '', source_excerpt: null },
          device_adjustments: { text: '', source_excerpt: null },
          patient_reported_issues: { text: '', source_excerpt: null },
          next_steps: { text: '', source_excerpt: null },
        }}
        confidence={55}
        rulesetDisclaimer={null}
      />,
    )
    expect(screen.getByText('Molestias referidas por el paciente')).toBeInTheDocument()
    expect(screen.getByText('Próximos pasos')).toBeInTheDocument()
    const emptyMessages = screen.getAllByText(/sin información registrada en esta sesión/i)
    expect(emptyMessages).toHaveLength(4)
  })

  it('tipo de artefacto no reconocido: muestra un aviso explícito, nunca contenido vacío en silencio', () => {
    render(
      <ArtifactContent
        // Simula un artifact_type futuro que el backend ya conoce pero
        // esta versión del frontend todavía no — JSON sin validar en
        // runtime, el tipo TS no lo impide realmente.
        artifactType={'future_artifact_type' as unknown as 'transcript'}
        content={{}}
        confidence={null}
        rulesetDisclaimer={null}
      />,
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/no reconocido/i)
  })
})
