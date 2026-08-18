import { describe, expect, it } from 'vitest'
import type { AIArtifactType } from '../../shared/api/types'
import {
  ARTIFACT_TYPE_LABELS,
  ARTIFACT_TYPE_ORDER,
  getArtifactTypeLabel,
  getArtifactTypeOrder,
} from './labels'

const ALL_SEVEN_TYPES: AIArtifactType[] = [
  'transcript',
  'summary',
  'patient_summary',
  'clinical_flags',
  'missing_information',
  'anamnesis',
  'session_notes',
]

describe('ARTIFACT_TYPE_LABELS', () => {
  it.each(ALL_SEVEN_TYPES)('%s tiene una etiqueta no vacía', (artifactType) => {
    expect(ARTIFACT_TYPE_LABELS[artifactType]).toBeTruthy()
  })

  it('no tiene entradas fuera de los 7 tipos conocidos por el backend', () => {
    expect(Object.keys(ARTIFACT_TYPE_LABELS).sort()).toEqual([...ALL_SEVEN_TYPES].sort())
  })
})

describe('ARTIFACT_TYPE_ORDER', () => {
  it('contiene exactamente los 7 tipos, sin repetidos', () => {
    expect([...ARTIFACT_TYPE_ORDER].sort()).toEqual([...ALL_SEVEN_TYPES].sort())
  })

  it('coincide con el orden canónico del pipeline backend (PIPELINE_STEP_ORDER)', () => {
    expect(ARTIFACT_TYPE_ORDER).toEqual([
      'transcript',
      'summary',
      'patient_summary',
      'clinical_flags',
      'missing_information',
      'anamnesis',
      'session_notes',
    ])
  })

  it('produce una posición determinista y distinta para cada uno de los 7 tipos', () => {
    const positions = ALL_SEVEN_TYPES.map((type) => getArtifactTypeOrder(type))
    expect(new Set(positions).size).toBe(7)
    expect(positions).toEqual([0, 1, 2, 3, 4, 5, 6])
  })
})

describe('fallback seguro para un artifact_type desconocido', () => {
  const unknownType = 'future_artifact_type' as unknown as AIArtifactType

  it('getArtifactTypeLabel nunca devuelve una cadena vacía', () => {
    expect(getArtifactTypeLabel(unknownType)).toBeTruthy()
  })

  it('getArtifactTypeOrder envía el tipo desconocido al final, nunca al principio', () => {
    const unknownPosition = getArtifactTypeOrder(unknownType)
    const knownPositions = ALL_SEVEN_TYPES.map((type) => getArtifactTypeOrder(type))
    expect(Math.max(...knownPositions)).toBeLessThan(unknownPosition)
  })
})
