import { describe, expect, it } from 'vitest'
import { ApiError } from './api/client'
import { describeActionError } from './apiErrorMessage'

describe('describeActionError', () => {
  it('403: etiqueta "No autorizado" y conserva el mensaje real del backend', () => {
    const error = new ApiError(403, {
      error: { code: 'forbidden', message: 'Un audiologist solo puede...' },
    })
    expect(describeActionError(error)).toEqual({
      label: 'No autorizado',
      message: 'Un audiologist solo puede...',
    })
  })

  it('409: etiqueta "Conflicto" y NUNCA reinterpreta el motivo real', () => {
    const error = new ApiError(409, {
      error: {
        code: 'conflict',
        message: 'Falta consentimiento válido de procesamiento IA para este paciente.',
      },
    })
    expect(describeActionError(error)).toEqual({
      label: 'Conflicto',
      message: 'Falta consentimiento válido de procesamiento IA para este paciente.',
    })
  })

  it('422: etiqueta "Solicitud inválida"', () => {
    const error = new ApiError(422, { error: { code: 'validation_error', message: 'x' } })
    expect(describeActionError(error).label).toBe('Solicitud inválida')
  })

  it('404: etiqueta "No encontrado"', () => {
    const error = new ApiError(404, { error: { code: 'not_found', message: 'x' } })
    expect(describeActionError(error).label).toBe('No encontrado')
  })

  it('otro status HTTP: etiqueta genérica con el código', () => {
    const error = new ApiError(500, { error: { code: 'internal_error', message: 'boom' } })
    expect(describeActionError(error)).toEqual({ label: 'Error (500)', message: 'boom' })
  })

  it('error que no es ApiError: "Error inesperado"', () => {
    expect(describeActionError(new Error('algo raro'))).toEqual({
      label: 'Error inesperado',
      message: 'algo raro',
    })
    expect(describeActionError('no-error-object').label).toBe('Error inesperado')
  })
})
