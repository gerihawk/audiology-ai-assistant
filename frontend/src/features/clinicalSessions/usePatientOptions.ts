import { useEffect, useState } from 'react'
import { listPatients } from '../../shared/api/patients'
import type { Patient } from '../../shared/api/types'

const MAX_PATIENT_OPTIONS = 100

/** Pacientes no archivados de la clínica activa, para poblar selectores.
 * Limitado a `MAX_PATIENT_OPTIONS`: suficiente para el MVP con datos
 * ficticios; un selector con búsqueda quedaría para una fase posterior. */
export function usePatientOptions(devUserId: string) {
  const [patients, setPatients] = useState<Patient[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    setStatus('loading')
    listPatients(devUserId, { limit: MAX_PATIENT_OPTIONS })
      .then((response) => {
        if (cancelled) return
        setPatients(response.items)
        setStatus('ready')
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [devUserId])

  return { patients, status }
}
