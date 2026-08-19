import { useCallback, useEffect, useState } from 'react'
import { listExpiredAudio, purgeExpiredAudio } from '../../shared/api/retention'
import { describeActionError } from '../../shared/apiErrorMessage'
import type { AudioRecording, Role } from '../../shared/api/types'
import { canManageRetention } from './permissions'

type LoadState = 'loading' | 'ready' | 'error'

interface Props {
  devUserId: string
  role: Role | undefined
}

/** Pantalla mínima de administración de retención (Fase 7.2) — mismos
 * campos que `AudioRecordingResponse` (backend), sin modelo visual nuevo:
 * listado de audio que supera `RETENTION_DAYS_DEFAULT` (incluidos los
 * estados atascados en `failed`/`uploaded`/`validating`/`transcribing`) +
 * purga manual con confirmación explícita, porque es un borrado físico
 * irreversible. */
export function ExpiredAudioSection({ devUserId, role }: Props) {
  const [items, setItems] = useState<AudioRecording[]>([])
  const [state, setState] = useState<LoadState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isPurging, setIsPurging] = useState(false)

  const load = useCallback(() => {
    setState('loading')
    setErrorMessage(null)
    listExpiredAudio(devUserId)
      .then((response) => {
        setItems(response.items)
        setState('ready')
      })
      .catch((error: unknown) => {
        const described = describeActionError(error)
        setErrorMessage(`${described.label}: ${described.message}`)
        setState('error')
      })
  }, [devUserId])

  const canManage = canManageRetention(role)

  useEffect(() => {
    if (canManage) load()
  }, [canManage, load])

  if (!canManage) return null

  async function handlePurge() {
    const confirmed = window.confirm(
      `¿Purgar ${items.length} grabación(es) de audio expirada(s)? Esta acción borra el fichero físico y no se puede deshacer.`,
    )
    if (!confirmed) return

    setIsPurging(true)
    setErrorMessage(null)
    try {
      await purgeExpiredAudio(devUserId)
      load()
    } catch (error) {
      const described = describeActionError(error)
      setErrorMessage(`${described.label}: ${described.message}`)
    } finally {
      setIsPurging(false)
    }
  }

  return (
    <section aria-label="Audio expirado">
      <h3>Audio expirado</h3>

      {state === 'loading' && <p role="status">Cargando audio expirado…</p>}
      {errorMessage && <p role="alert">{errorMessage}</p>}

      {state === 'ready' && (
        <>
          {items.length === 0 ? (
            <p>No hay audio que supere el periodo de retención.</p>
          ) : (
            <>
              <ul aria-label="Grabaciones de audio expiradas">
                {items.map((item) => (
                  <li key={item.id}>
                    {item.original_filename} — {item.status} — {item.size_bytes} bytes — subido el{' '}
                    {new Date(item.uploaded_at).toLocaleString()}
                    {item.failure_reason && <> — motivo de fallo: {item.failure_reason}</>}
                  </li>
                ))}
              </ul>
              <button type="button" onClick={handlePurge} disabled={isPurging}>
                {isPurging ? 'Purgando…' : 'Purgar audio expirado'}
              </button>
            </>
          )}
        </>
      )}
    </section>
  )
}
