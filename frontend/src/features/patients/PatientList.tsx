import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { archivePatient, listPatients, restorePatient } from '../../shared/api/patients'
import type { Patient, Role } from '../../shared/api/types'
import { canArchivePatient, canCreatePatient, canRestorePatient } from './permissions'

const PAGE_SIZE = 10

interface PatientListProps {
  devUserId: string
  role: Role | undefined
}

type LoadState = 'loading' | 'ready' | 'error'

export function PatientList({ devUserId, role }: PatientListProps) {
  const [search, setSearch] = useState('')
  const [includeArchived, setIncludeArchived] = useState(false)
  const [offset, setOffset] = useState(0)
  const [items, setItems] = useState<Patient[]>([])
  const [total, setTotal] = useState(0)
  const [state, setState] = useState<LoadState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const load = useCallback(() => {
    setState('loading')
    setErrorMessage(null)
    listPatients(devUserId, {
      search: search || undefined,
      includeArchived,
      limit: PAGE_SIZE,
      offset,
    })
      .then((response) => {
        setItems(response.items)
        setTotal(response.total)
        setState('ready')
      })
      .catch((error: unknown) => {
        setErrorMessage(error instanceof Error ? error.message : 'No se pudo cargar el listado.')
        setState('error')
      })
  }, [devUserId, search, includeArchived, offset])

  useEffect(() => {
    load()
  }, [load])

  async function handleArchive(patient: Patient) {
    const confirmed = window.confirm(
      `¿Archivar al paciente ${patient.internal_code}? Podrás restaurarlo más adelante.`,
    )
    if (!confirmed) return
    setActionError(null)
    try {
      await archivePatient(devUserId, patient.id)
      load()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'No se pudo archivar el paciente.')
    }
  }

  async function handleRestore(patient: Patient) {
    setActionError(null)
    try {
      await restorePatient(devUserId, patient.id)
      load()
    } catch (error) {
      setActionError(error instanceof Error ? error.message : 'No se pudo restaurar el paciente.')
    }
  }

  return (
    <div>
      <div className="patient-list-toolbar">
        <div>
          <label htmlFor="patient-search">Buscar</label>
          <input
            id="patient-search"
            type="search"
            value={search}
            onChange={(event) => {
              setOffset(0)
              setSearch(event.target.value)
            }}
            placeholder="Código interno o nombre"
          />
        </div>
        <div>
          <label htmlFor="include-archived">
            <input
              id="include-archived"
              type="checkbox"
              checked={includeArchived}
              onChange={(event) => {
                setOffset(0)
                setIncludeArchived(event.target.checked)
              }}
            />
            Mostrar archivados
          </label>
        </div>
        {canCreatePatient(role) && <Link to="/patients/new">Crear paciente</Link>}
      </div>

      {actionError && <p role="alert">{actionError}</p>}

      {state === 'loading' && <p role="status">Cargando pacientes…</p>}
      {state === 'error' && <p role="alert">Error al cargar pacientes: {errorMessage}</p>}
      {state === 'ready' && items.length === 0 && (
        <p>No hay pacientes que coincidan con la búsqueda.</p>
      )}

      {state === 'ready' && items.length > 0 && (
        <table>
          <caption className="visually-hidden">Listado de pacientes</caption>
          <thead>
            <tr>
              <th scope="col">Código interno</th>
              <th scope="col">Nombre</th>
              <th scope="col">Estado</th>
              <th scope="col">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {items.map((patient) => (
              <tr key={patient.id}>
                <td>{patient.internal_code}</td>
                <td>{patient.display_name ?? '—'}</td>
                <td>{patient.is_archived ? 'Archivado' : 'Activo'}</td>
                <td>
                  <Link to={`/patients/${patient.id}`}>Ver detalle de {patient.internal_code}</Link>
                  {!patient.is_archived && canArchivePatient(role) && (
                    <button type="button" onClick={() => handleArchive(patient)}>
                      Archivar {patient.internal_code}
                    </button>
                  )}
                  {patient.is_archived && canRestorePatient(role) && (
                    <button type="button" onClick={() => handleRestore(patient)}>
                      Restaurar {patient.internal_code}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {state === 'ready' && total > PAGE_SIZE && (
        <nav aria-label="Paginación de pacientes">
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
