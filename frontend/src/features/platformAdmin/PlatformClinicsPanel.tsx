import { useCallback, useEffect, useState } from 'react'
import { describeActionError } from '../../shared/apiErrorMessage'
import type { PlatformClinic } from '../../shared/api/types'
import { listPlatformClinics, setPlatformClinicActive } from './api'

type LoadState = 'loading' | 'ready' | 'error'

/** Panel del candidato 1 (Fase 14): tabla de TODAS las clínicas de la
 * plataforma, con un botón para activar/desactivar cada una. Sin props —
 * a diferencia de `BillingPanel` (que recibe `devUserId`/`role` porque
 * vive dentro de una clínica concreta), este panel no tiene ningún
 * concepto de "clínica actual": la identidad que lo protege es el
 * operador de plataforma (`PlatformAuthContext`), resuelto una única vez
 * más arriba, en `PlatformAdminPage`. */
export function PlatformClinicsPanel() {
  const [clinics, setClinics] = useState<PlatformClinic[]>([])
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  // Id de la clínica cuyo PATCH está en vuelo — deshabilita solo su propio
  // botón, no la tabla entera, para poder ver de un vistazo qué fila se
  // está actualizando.
  const [updatingClinicId, setUpdatingClinicId] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoadState('loading')
    setErrorMessage(null)
    listPlatformClinics()
      .then((response) => {
        setClinics(response.items)
        setLoadState('ready')
      })
      .catch((error: unknown) => {
        const described = describeActionError(error)
        setErrorMessage(`${described.label}: ${described.message}`)
        setLoadState('error')
      })
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function handleToggle(clinic: PlatformClinic) {
    setUpdatingClinicId(clinic.id)
    setErrorMessage(null)
    try {
      const updated = await setPlatformClinicActive(clinic.id, !clinic.is_active)
      setClinics((current) => current.map((item) => (item.id === updated.id ? updated : item)))
    } catch (error) {
      const described = describeActionError(error)
      setErrorMessage(`${described.label}: ${described.message}`)
    } finally {
      setUpdatingClinicId(null)
    }
  }

  return (
    <div>
      <h2>Clínicas</h2>

      {errorMessage && <p role="alert">{errorMessage}</p>}

      {loadState === 'loading' && <p role="status">Cargando clínicas…</p>}

      {loadState === 'ready' && (
        <table>
          <caption>{clinics.length} clínica(s) registradas en la plataforma</caption>
          <thead>
            <tr>
              <th scope="col">Nombre</th>
              <th scope="col">Código</th>
              <th scope="col">Estado</th>
              <th scope="col">Nivel</th>
              <th scope="col">Sesiones usadas (periodo)</th>
              <th scope="col">Acción</th>
            </tr>
          </thead>
          <tbody>
            {clinics.map((clinic) => (
              <tr key={clinic.id}>
                <td>{clinic.name}</td>
                <td>{clinic.code}</td>
                <td>
                  {clinic.is_active ? 'Activa' : 'Desactivada'}
                  {clinic.subscription_status ? ` (${clinic.subscription_status})` : ''}
                </td>
                <td>{clinic.plan ?? '—'}</td>
                <td>{clinic.sessions_used_this_period}</td>
                <td>
                  <button
                    type="button"
                    onClick={() => void handleToggle(clinic)}
                    disabled={updatingClinicId !== null}
                  >
                    {updatingClinicId === clinic.id
                      ? 'Actualizando…'
                      : clinic.is_active
                        ? 'Desactivar'
                        : 'Activar'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
