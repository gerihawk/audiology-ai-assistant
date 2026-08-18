import { useEffect, useState } from 'react'
import { getPatient } from '../../shared/api/patients'
import type { Patient } from '../../shared/api/types'

type PatientState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; patient: Patient }

/** Resuelve un paciente por id para páginas montadas directamente por URL
 * (reload/deep-link). Un id inexistente o inaccesible para el usuario
 * ficticio activo se refleja como `status: 'error'` con el mensaje del
 * backend (403/404), sin lógica de navegación privilegiada. */
export function usePatient(devUserId: string, patientId: string) {
  const [state, setState] = useState<PatientState>({ status: 'loading' })

  useEffect(() => {
    if (!devUserId) return
    let cancelled = false
    setState({ status: 'loading' })
    getPatient(devUserId, patientId)
      .then((patient) => {
        if (!cancelled) setState({ status: 'ready', patient })
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({
            status: 'error',
            message: error instanceof Error ? error.message : 'No se pudo cargar el paciente.',
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [devUserId, patientId])

  const setPatient = (patient: Patient) => setState({ status: 'ready', patient })

  return { ...state, setPatient }
}
