import type { ClinicalSessionStatus, DevUser, Patient, SessionType } from '../../shared/api/types'
import { SESSION_TYPE_LABELS, SESSION_TYPES, STATUS_LABELS, STATUSES } from './labels'

export interface ClinicalSessionFiltersState {
  patientId: string
  professionalId: string
  status: ClinicalSessionStatus | ''
  sessionType: SessionType | ''
  scheduledFrom: string
  scheduledTo: string
  search: string
  includeArchived: boolean
}

export const EMPTY_CLINICAL_SESSION_FILTERS: ClinicalSessionFiltersState = {
  patientId: '',
  professionalId: '',
  status: '',
  sessionType: '',
  scheduledFrom: '',
  scheduledTo: '',
  search: '',
  includeArchived: false,
}

interface Props {
  value: ClinicalSessionFiltersState
  onChange: (next: ClinicalSessionFiltersState) => void
  professionalOptions: DevUser[]
  patientOptions: Patient[]
  /** Cuando se muestra dentro del detalle de un paciente, el filtro de
   * paciente queda fijo y no se ofrece el selector. */
  lockedPatient?: Patient
}

export function ClinicalSessionFilters({
  value,
  onChange,
  professionalOptions,
  patientOptions,
  lockedPatient,
}: Props) {
  function set<K extends keyof ClinicalSessionFiltersState>(
    key: K,
    fieldValue: ClinicalSessionFiltersState[K],
  ) {
    onChange({ ...value, [key]: fieldValue })
  }

  return (
    <div className="clinical-session-filters">
      {!lockedPatient && (
        <div>
          <label htmlFor="cs-filter-patient">Paciente</label>
          <select
            id="cs-filter-patient"
            value={value.patientId}
            onChange={(event) => set('patientId', event.target.value)}
          >
            <option value="">Todos</option>
            {patientOptions.map((patient) => (
              <option key={patient.id} value={patient.id}>
                {patient.internal_code}
                {patient.display_name ? ` — ${patient.display_name}` : ''}
              </option>
            ))}
          </select>
        </div>
      )}

      <div>
        <label htmlFor="cs-filter-professional">Profesional</label>
        <select
          id="cs-filter-professional"
          value={value.professionalId}
          onChange={(event) => set('professionalId', event.target.value)}
        >
          <option value="">Todos</option>
          {professionalOptions.map((user) => (
            <option key={user.id} value={user.id}>
              {user.display_name}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="cs-filter-status">Estado</label>
        <select
          id="cs-filter-status"
          value={value.status}
          onChange={(event) => set('status', event.target.value as ClinicalSessionStatus | '')}
        >
          <option value="">Todos</option>
          {STATUSES.map((status) => (
            <option key={status} value={status}>
              {STATUS_LABELS[status]}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="cs-filter-type">Tipo</label>
        <select
          id="cs-filter-type"
          value={value.sessionType}
          onChange={(event) => set('sessionType', event.target.value as SessionType | '')}
        >
          <option value="">Todos</option>
          {SESSION_TYPES.map((type) => (
            <option key={type} value={type}>
              {SESSION_TYPE_LABELS[type]}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="cs-filter-scheduled-from">Programada desde</label>
        <input
          id="cs-filter-scheduled-from"
          type="date"
          value={value.scheduledFrom}
          onChange={(event) => set('scheduledFrom', event.target.value)}
        />
      </div>

      <div>
        <label htmlFor="cs-filter-scheduled-to">Programada hasta</label>
        <input
          id="cs-filter-scheduled-to"
          type="date"
          value={value.scheduledTo}
          onChange={(event) => set('scheduledTo', event.target.value)}
        />
      </div>

      <div>
        <label htmlFor="cs-filter-search">Buscar</label>
        <input
          id="cs-filter-search"
          type="search"
          value={value.search}
          onChange={(event) => set('search', event.target.value)}
          placeholder="Título o notas administrativas"
        />
      </div>

      <div>
        <label htmlFor="cs-filter-archived">
          <input
            id="cs-filter-archived"
            type="checkbox"
            checked={value.includeArchived}
            onChange={(event) => set('includeArchived', event.target.checked)}
          />
          Mostrar archivadas
        </label>
      </div>
    </div>
  )
}
