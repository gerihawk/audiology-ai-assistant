import { useEffect, useState } from 'react'
import { listConsents } from '../../shared/api/consents'
import type { Consent, DevUser } from '../../shared/api/types'
import { formatDateTime, professionalName } from '../clinicalSessions/format'
import { CONSENT_TYPE_LABELS } from './labels'

interface Props {
  devUserId: string
  patientId: string
  refreshToken: number
  professionalOptions: DevUser[]
}

type LoadState = 'loading' | 'ready' | 'error'

/** Histórico completo de consentimientos del paciente (append-only: nunca
 * se oculta un registro revocado, ver `ConsentRepository.get_latest`). */
export function ConsentList({ devUserId, patientId, refreshToken, professionalOptions }: Props) {
  const [items, setItems] = useState<Consent[]>([])
  const [state, setState] = useState<LoadState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setState('loading')
    setErrorMessage(null)
    listConsents(devUserId, patientId)
      .then((response) => {
        if (cancelled) return
        setItems(response.items)
        setState('ready')
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setErrorMessage(error instanceof Error ? error.message : 'No se pudo cargar el histórico.')
        setState('error')
      })
    return () => {
      cancelled = true
    }
  }, [devUserId, patientId, refreshToken])

  if (state === 'loading') return <p role="status">Cargando consentimientos…</p>
  if (state === 'error') {
    return <p role="alert">Error al cargar los consentimientos: {errorMessage}</p>
  }
  if (items.length === 0) {
    return <p>Todavía no se ha registrado ningún consentimiento.</p>
  }

  return (
    <table>
      <caption className="visually-hidden">Histórico de consentimientos</caption>
      <thead>
        <tr>
          <th scope="col">Tipo</th>
          <th scope="col">Otorgado</th>
          <th scope="col">Versión</th>
          <th scope="col">Quién</th>
          <th scope="col">Cuándo</th>
        </tr>
      </thead>
      <tbody>
        {items.map((consent) => (
          <tr key={consent.id}>
            <td>{CONSENT_TYPE_LABELS[consent.consent_type]}</td>
            <td>{consent.granted ? 'Sí' : 'No'}</td>
            <td>{consent.consent_version ?? '—'}</td>
            <td>{professionalName(consent.granted_by, professionalOptions)}</td>
            <td>{formatDateTime(consent.recorded_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
