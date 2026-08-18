import { describe, expect, it } from 'vitest'
import { sessionTypeLabel } from './format'

describe('sessionTypeLabel', () => {
  it('null se presenta como "Sin especificar" (solo en presentación)', () => {
    expect(sessionTypeLabel(null)).toBe('Sin especificar')
  })

  it('un session_type conocido usa la misma etiqueta que clinicalSessions', () => {
    expect(sessionTypeLabel('initial_assessment')).toBe('Valoración inicial')
    expect(sessionTypeLabel('follow_up')).toBe('Seguimiento')
  })

  it('un valor desconocido se muestra tal cual, nunca en blanco', () => {
    expect(sessionTypeLabel('tipo_futuro')).toBe('tipo_futuro')
  })
})
