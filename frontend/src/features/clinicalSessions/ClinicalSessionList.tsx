import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listClinicalSessions } from '../../shared/api/clinicalSessions'
import type { ClinicalSession, DevUser, Patient, Role } from '../../shared/api/types'
import { ClinicalSessionBadge } from './ClinicalSessionBadge'
import { ClinicalSessionFilters, EMPTY_CLINICAL_SESSION_FILTERS } from './ClinicalSessionFilters'
import type { ClinicalSessionFiltersState } from './ClinicalSessionFilters'
import { formatDateTime, professionalName } from './format'
import { SESSION_TYPE_LABELS } from './labels'
import { canCreateSession } from './permissions'

const PAGE_SIZE = 10

type LoadState = 'loading' | 'ready' | 'error'

interface Props {
  devUserId: string
  role: Role | undefined
  refreshToken: number
  patientOptions: Patient[]
  professionalOptions: DevUser[]
  /** Cuando se muestra dentro del detalle de un paciente, restringe el
   * listado a ese paciente y oculta el selector de paciente en los filtros. */
  lockedPatient?: Patient
  onCreate: () => void
}

export function ClinicalSessionList({
  devUserId,
  role,
  refreshToken,
  patientOptions,
  professionalOptions,
  lockedPatient,
  onCreate,
}: Props) {
  const [filters, setFilters] = useState<ClinicalSessionFiltersState>({
    ...EMPTY_CLINICAL_SESSION_FILTERS,
    patientId: lockedPatient?.id ?? '',
  })
  const [offset, setOffset] = useState(0)
  const [items, setItems] = useState<ClinicalSession[]>([])
  const [total, setTotal] = useState(0)
  const [state, setState] = useState<LoadState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const load = useCallback(() => {
    setState('loading')
    setErrorMessage(null)
    listClinicalSessions(devUserId, {
      patientId: (lockedPatient?.id ?? filters.patientId) || undefined,
      professionalId: filters.professionalId || undefined,
      status: filters.status || undefined,
      sessionType: filters.sessionType || undefined,
      scheduledFrom: filters.scheduledFrom || undefined,
      scheduledTo: filters.scheduledTo || undefined,
      search: filters.search || undefined,
      includeArchived: filters.includeArchived,
      limit: PAGE_SIZE,
      offset,
    })
      .then((response) => {
        setItems(response.items)
        setTotal(response.total)
        setState('ready')
      })
      .catch((error: unknown) => {
        setErrorMessage(
          error instanceof Error ? error.message : 'No se pudo cargar el listado de sesiones.',
        )
        setState('error')
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [devUserId, filters, offset, refreshToken, lockedPatient?.id])

  useEffect(() => {
    load()
  }, [load])

  function handleFiltersChange(next: ClinicalSessionFiltersState) {
    setOffset(0)
    setFilters(next)
  }

  return (
    <div>
      <div className="patient-list-toolbar">
        <ClinicalSessionFilters
          value={filters}
          onChange={handleFiltersChange}
          professionalOptions={professionalOptions}
          patientOptions={patientOptions}
          lockedPatient={lockedPatient}
        />
        {canCreateSession(role) && (
          <button type="button" onClick={onCreate}>
            Crear sesión clínica
          </button>
        )}
      </div>

      {state === 'loading' && <p role="status">Cargando sesiones clínicas…</p>}
      {state === 'error' && <p role="alert">Error al cargar sesiones clínicas: {errorMessage}</p>}
      {state === 'ready' && items.length === 0 && (
        <p>No hay sesiones clínicas que coincidan con los filtros.</p>
      )}

      {state === 'ready' && items.length > 0 && (
        <table>
          <caption className="visually-hidden">Listado de sesiones clínicas</caption>
          <thead>
            <tr>
              <th scope="col">Tipo</th>
              <th scope="col">Estado</th>
              <th scope="col">Profesional responsable</th>
              <th scope="col">Programada</th>
              <th scope="col">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {items.map((session) => (
              <tr key={session.id}>
                <td>{SESSION_TYPE_LABELS[session.session_type]}</td>
                <td>
                  <ClinicalSessionBadge status={session.status} />
                  {session.is_archived && ' (archivada)'}
                </td>
                <td>{professionalName(session.professional_id, professionalOptions)}</td>
                <td>{formatDateTime(session.scheduled_at)}</td>
                <td>
                  <Link to={`/clinical-sessions/${session.id}`}>Ver detalle</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {state === 'ready' && total > PAGE_SIZE && (
        <nav aria-label="Paginación de sesiones clínicas">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Anterior
          </button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} de {total}
          </span>
          <button
            type="button"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Siguiente
          </button>
        </nav>
      )}
    </div>
  )
}
