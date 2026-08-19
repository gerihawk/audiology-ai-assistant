import { useCallback, useEffect, useState } from 'react'
import { listIntegrations } from '../../shared/api/integrations'
import { describeActionError } from '../../shared/apiErrorMessage'
import type { IntegrationConfig, Role } from '../../shared/api/types'
import { canManageIntegrations } from './permissions'

type LoadState = 'loading' | 'ready' | 'error'

interface Props {
  devUserId: string
  role: Role | undefined
}

/** Pantalla mínima de administración de integraciones (Fase 7.3) — tabla
 * de solo lectura del estado de las dos integraciones abstractas
 * (`patient_record`/`calendar`). Sin formulario de `PATCH` esta ronda
 * (docs/development-plan.md: "solo lectura del estado mock"). */
export function IntegrationsList({ devUserId, role }: Props) {
  const [items, setItems] = useState<IntegrationConfig[]>([])
  const [state, setState] = useState<LoadState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const load = useCallback(() => {
    setState('loading')
    setErrorMessage(null)
    listIntegrations(devUserId)
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

  const canManage = canManageIntegrations(role)

  useEffect(() => {
    if (canManage) load()
  }, [canManage, load])

  if (!canManage) return null

  return (
    <section aria-label="Integraciones">
      <h3>Integraciones</h3>

      {state === 'loading' && <p role="status">Cargando integraciones…</p>}
      {errorMessage && <p role="alert">{errorMessage}</p>}

      {state === 'ready' &&
        (items.length === 0 ? (
          <p>No hay integraciones configuradas.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Integración</th>
                <th>Proveedor activo</th>
                <th>Habilitada</th>
                <th>Actualizada por</th>
                <th>Actualizada el</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.integration_name}</td>
                  <td>{item.active_provider}</td>
                  <td>{item.enabled ? 'Sí' : 'No'}</td>
                  <td>{item.updated_by}</td>
                  <td>{new Date(item.updated_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
    </section>
  )
}
