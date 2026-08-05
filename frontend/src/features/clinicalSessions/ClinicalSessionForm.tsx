import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../../shared/api/client'
import { createClinicalSession, updateClinicalSession } from '../../shared/api/clinicalSessions'
import type { ClinicalSession, DevUser, Patient, Role, SessionType } from '../../shared/api/types'
import { canChangeProfessional, editableFieldsForStatus } from './permissions'
import { SESSION_TYPE_LABELS, SESSION_TYPES } from './labels'

type InitialStatus = 'scheduled' | 'in_progress' | 'completed'

const INITIAL_STATUS_OPTIONS: { value: InitialStatus; label: string }[] = [
  { value: 'scheduled', label: 'Programada' },
  { value: 'in_progress', label: 'En curso' },
  { value: 'completed', label: 'Completada' },
]

interface Props {
  devUserId: string
  mode: 'create' | 'edit'
  session?: ClinicalSession
  currentUserId: string | undefined
  role: Role | undefined
  patientOptions: Patient[]
  professionalOptions: DevUser[]
  /** Paciente fijo al crear desde el detalle de un paciente concreto. */
  lockedPatient?: Patient
  onDone: (session: ClinicalSession) => void
  onCancel: () => void
}

function toDatetimeLocalValue(isoValue: string | null | undefined): string {
  if (!isoValue) return ''
  return isoValue.slice(0, 16)
}

function fromDatetimeLocalValue(value: string): string | null {
  if (!value) return null
  return value.length === 16 ? `${value}:00` : value
}

export function ClinicalSessionForm({
  devUserId,
  mode,
  session,
  currentUserId,
  role,
  patientOptions,
  professionalOptions,
  lockedPatient,
  onDone,
  onCancel,
}: Props) {
  const editable = mode === 'edit' && session ? editableFieldsForStatus(session.status) : 'all'
  const canEditProfessional = mode === 'create' || canChangeProfessional(role)

  const [patientId, setPatientId] = useState(lockedPatient?.id ?? session?.patient_id ?? '')
  const [professionalId, setProfessionalId] = useState(
    session?.professional_id ?? currentUserId ?? '',
  )
  const [sessionType, setSessionType] = useState<SessionType>(
    session?.session_type ?? 'initial_assessment',
  )
  const [initialStatus, setInitialStatus] = useState<InitialStatus>('scheduled')
  const [scheduledAt, setScheduledAt] = useState(toDatetimeLocalValue(session?.scheduled_at))
  const [title, setTitle] = useState(session?.title ?? '')
  const [administrativeNotes, setAdministrativeNotes] = useState(
    session?.administrative_notes ?? '',
  )
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  if (mode === 'edit' && editable === 'none') {
    return <p>Esta sesión ya no admite edición de metadatos en su estado actual.</p>
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return
    setSubmitting(true)
    setFormError(null)
    setFieldErrors({})

    try {
      let result: ClinicalSession
      if (mode === 'create') {
        result = await createClinicalSession(devUserId, {
          patient_id: patientId,
          professional_id: professionalId,
          session_type: sessionType,
          status: initialStatus,
          scheduled_at: fromDatetimeLocalValue(scheduledAt),
          title: title || null,
          administrative_notes: administrativeNotes || null,
        })
      } else {
        const payload: Parameters<typeof updateClinicalSession>[2] = {
          title: title || null,
          administrative_notes: administrativeNotes || null,
        }
        if (editable === 'all') {
          payload.session_type = sessionType
          payload.scheduled_at = fromDatetimeLocalValue(scheduledAt)
          if (canEditProfessional) payload.professional_id = professionalId
        }
        result = await updateClinicalSession(devUserId, (session as ClinicalSession).id, payload)
      }
      onDone(result)
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.code === 'conflict' && error.field) {
          setFieldErrors({ [error.field]: error.message })
        } else if (error.code === 'validation_error' && error.details) {
          const next: Record<string, string> = {}
          for (const detail of error.details) {
            const field = detail.loc?.[detail.loc.length - 1]
            if (typeof field === 'string') next[field] = detail.msg
          }
          setFieldErrors(next)
        } else {
          setFormError(error.message)
        }
      } else {
        setFormError('No se pudo guardar la sesión clínica.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const showFullFields = mode === 'create' || editable === 'all'

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={mode === 'create' ? 'Crear sesión clínica' : 'Editar sesión clínica'}
    >
      <h2>{mode === 'create' ? 'Crear sesión clínica ficticia' : 'Editar sesión clínica'}</h2>
      <p>
        Contenido administrativo únicamente. No incluye anamnesis, notas clínicas ni datos
        diagnósticos.
      </p>

      {formError && <p role="alert">{formError}</p>}

      {mode === 'create' && (
        <div>
          <label htmlFor="cs-patient">Paciente *</label>
          {lockedPatient ? (
            <input
              id="cs-patient"
              value={`${lockedPatient.internal_code}${
                lockedPatient.display_name ? ` — ${lockedPatient.display_name}` : ''
              }`}
              disabled
              readOnly
            />
          ) : (
            <select
              id="cs-patient"
              value={patientId}
              onChange={(event) => setPatientId(event.target.value)}
              required
              aria-invalid={Boolean(fieldErrors.patient_id)}
              aria-describedby={fieldErrors.patient_id ? 'cs-patient-error' : undefined}
            >
              <option value="">Selecciona un paciente</option>
              {patientOptions.map((patient) => (
                <option key={patient.id} value={patient.id}>
                  {patient.internal_code}
                  {patient.display_name ? ` — ${patient.display_name}` : ''}
                </option>
              ))}
            </select>
          )}
          {fieldErrors.patient_id && (
            <p id="cs-patient-error" role="alert">
              {fieldErrors.patient_id}
            </p>
          )}
        </div>
      )}

      <div>
        <label htmlFor="cs-professional">Profesional responsable *</label>
        <select
          id="cs-professional"
          value={professionalId}
          onChange={(event) => setProfessionalId(event.target.value)}
          required
          disabled={mode === 'edit' && !canEditProfessional}
          aria-invalid={Boolean(fieldErrors.professional_id)}
          aria-describedby={fieldErrors.professional_id ? 'cs-professional-error' : undefined}
        >
          <option value="">Selecciona un profesional</option>
          {professionalOptions.map((user) => (
            <option key={user.id} value={user.id}>
              {user.display_name}
            </option>
          ))}
        </select>
        {fieldErrors.professional_id && (
          <p id="cs-professional-error" role="alert">
            {fieldErrors.professional_id}
          </p>
        )}
      </div>

      {showFullFields && (
        <div>
          <label htmlFor="cs-type">Tipo de sesión *</label>
          <select
            id="cs-type"
            value={sessionType}
            onChange={(event) => setSessionType(event.target.value as SessionType)}
            required
          >
            {SESSION_TYPES.map((type) => (
              <option key={type} value={type}>
                {SESSION_TYPE_LABELS[type]}
              </option>
            ))}
          </select>
        </div>
      )}

      {mode === 'create' && (
        <div>
          <label htmlFor="cs-initial-status">Estado inicial *</label>
          <select
            id="cs-initial-status"
            value={initialStatus}
            onChange={(event) => setInitialStatus(event.target.value as InitialStatus)}
          >
            {INITIAL_STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {showFullFields && (
        <div>
          <label htmlFor="cs-scheduled-at">Fecha y hora programada</label>
          <input
            id="cs-scheduled-at"
            type="datetime-local"
            value={scheduledAt}
            onChange={(event) => setScheduledAt(event.target.value)}
          />
        </div>
      )}

      <div>
        <label htmlFor="cs-title">Título</label>
        <input
          id="cs-title"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={200}
          aria-invalid={Boolean(fieldErrors.title)}
          aria-describedby={fieldErrors.title ? 'cs-title-error' : undefined}
        />
        {fieldErrors.title && (
          <p id="cs-title-error" role="alert">
            {fieldErrors.title}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="cs-notes">Notas administrativas</label>
        <textarea
          id="cs-notes"
          value={administrativeNotes}
          onChange={(event) => setAdministrativeNotes(event.target.value)}
          maxLength={2000}
          aria-invalid={Boolean(fieldErrors.administrative_notes)}
          aria-describedby={fieldErrors.administrative_notes ? 'cs-notes-error' : undefined}
        />
        {fieldErrors.administrative_notes && (
          <p id="cs-notes-error" role="alert">
            {fieldErrors.administrative_notes}
          </p>
        )}
      </div>

      <div>
        <button type="submit" disabled={submitting}>
          {mode === 'create' ? 'Crear sesión' : 'Guardar cambios'}
        </button>
        <button type="button" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
      </div>
    </form>
  )
}
