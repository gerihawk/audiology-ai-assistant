import { useCallback, useEffect, useState } from 'react'
import { listInvitations, revokeInvitation } from '../../shared/api/invitations'
import { describeActionError } from '../../shared/apiErrorMessage'
import type { InvitationSummary } from '../../shared/api/types'

type LoadState = 'loading' | 'ready' | 'error'

interface Props {
  clinicId: string
  devUserId: string
  /** Incrementado por `InvitationsPage` tras una invitación nueva o una
   * revocación en otra instancia — fuerza una recarga sin duplicar la
   * lógica de `load` en el padre (mismo rol que una `key`, pero sin
   * remontar el componente). */
  reloadSignal: number
}

const ROLE_LABELS: Record<string, string> = {
  audiologist: 'Audiólogo',
  viewer: 'Solo lectura',
}

/** Lista de invitaciones pendientes de la clínica (Fase 12, hito 12.3) —
 * mismo patrón de carga que `IntegrationsList`. Solo pendientes: el
 * backend (`InvitationRepository.list_pending_for_clinic`) ya filtra
 * `accepted_at IS NULL`, así que una invitación aceptada o revocada
 * simplemente desaparece de la lista en la siguiente carga. */
export function InvitationsList({ clinicId, devUserId, reloadSignal }: Props) {
  const [items, setItems] = useState<InvitationSummary[]>([])
  const [state, setState] = useState<LoadState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [revokingId, setRevokingId] = useState<string | null>(null)

  const load = useCallback(() => {
    setState('loading')
    setErrorMessage(null)
    listInvitations(clinicId, devUserId)
      .then((response) => {
        setItems(response.items)
        setState('ready')
      })
      .catch((error: unknown) => {
        const described = describeActionError(error)
        setErrorMessage(`${described.label}: ${described.message}`)
        setState('error')
      })
  }, [clinicId, devUserId])

  useEffect(() => {
    load()
    // `reloadSignal` es una señal pura (no se lee su valor, solo se observa
    // que cambió) — se incluye a propósito en las dependencias.
  }, [load, reloadSignal])

  async function handleRevoke(invitationId: string) {
    setRevokingId(invitationId)
    setErrorMessage(null)
    try {
      await revokeInvitation(clinicId, invitationId, devUserId)
      load()
    } catch (error) {
      const described = describeActionError(error)
      setErrorMessage(`${described.label}: ${described.message}`)
    } finally {
      setRevokingId(null)
    }
  }

  return (
    <section aria-label="Invitaciones pendientes">
      <h3>Invitaciones pendientes</h3>

      {state === 'loading' && <p role="status">Cargando invitaciones…</p>}
      {errorMessage && <p role="alert">{errorMessage}</p>}

      {state === 'ready' &&
        (items.length === 0 ? (
          <p>No hay invitaciones pendientes.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Email</th>
                <th>Rol</th>
                <th>Expira</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.email}</td>
                  <td>{ROLE_LABELS[item.role] ?? item.role}</td>
                  <td>
                    {new Date(item.expires_at).toLocaleString()}
                    {item.is_expired && ' (caducada)'}
                  </td>
                  <td>
                    <button
                      type="button"
                      onClick={() => void handleRevoke(item.id)}
                      disabled={revokingId === item.id}
                    >
                      {revokingId === item.id ? 'Revocando…' : 'Revocar'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
    </section>
  )
}
