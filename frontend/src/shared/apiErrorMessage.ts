import { ApiError } from './api/client'

export interface ActionErrorDescription {
  label: string
  message: string
}

/** Traduce el error de una acción (run-pipeline, edición humana,
 * propose-anamnesis-update, exportación individual/longitudinal) a una
 * etiqueta + mensaje visibles. Nunca reinterpreta el motivo: el mensaje
 * siempre es el que ya devuelve el backend tal cual (`ApiError.message`) —
 * especialmente importante para 409 (consentimiento, ejecución en curso,
 * configuración de proveedor, baseline obsoleto, límite de sesiones
 * exportables…), donde el backend ya explica la causa real. */
export function describeActionError(error: unknown): ActionErrorDescription {
  if (error instanceof ApiError) {
    switch (error.status) {
      case 403:
        return { label: 'No autorizado', message: error.message }
      case 404:
        return { label: 'No encontrado', message: error.message }
      case 409:
        return { label: 'Conflicto', message: error.message }
      case 422:
        return { label: 'Solicitud inválida', message: error.message }
      default:
        return { label: `Error (${error.status})`, message: error.message }
    }
  }
  return {
    label: 'Error inesperado',
    message: error instanceof Error ? error.message : 'Ha ocurrido un error inesperado.',
  }
}
