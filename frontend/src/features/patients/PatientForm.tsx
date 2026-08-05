import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../../shared/api/client'
import { createPatient, updatePatient } from '../../shared/api/patients'
import type { Patient, Sex } from '../../shared/api/types'

interface PatientFormProps {
  devUserId: string
  mode: 'create' | 'edit'
  patient?: Patient
  onDone: (patient: Patient) => void
  onCancel: () => void
}

const SEX_OPTIONS: { value: Sex; label: string }[] = [
  { value: 'female', label: 'Femenino' },
  { value: 'male', label: 'Masculino' },
  { value: 'other', label: 'Otro' },
  { value: 'unspecified', label: 'No especificado' },
]

export function PatientForm({ devUserId, mode, patient, onDone, onCancel }: PatientFormProps) {
  const [internalCode, setInternalCode] = useState(patient?.internal_code ?? '')
  const [displayName, setDisplayName] = useState(patient?.display_name ?? '')
  const [birthYear, setBirthYear] = useState(patient?.birth_year ? String(patient.birth_year) : '')
  const [sex, setSex] = useState<Sex | ''>(patient?.sex ?? '')
  const [notes, setNotes] = useState(patient?.notes ?? '')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setFormError(null)
    setFieldErrors({})

    const payload = {
      internal_code: internalCode,
      display_name: displayName || null,
      birth_year: birthYear ? Number(birthYear) : null,
      sex: sex || null,
      notes: notes || null,
    }

    try {
      const result =
        mode === 'create'
          ? await createPatient(devUserId, payload)
          : await updatePatient(devUserId, (patient as Patient).id, payload)
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
        setFormError('No se pudo guardar el paciente.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-label={mode === 'create' ? 'Crear paciente' : 'Editar paciente'}
    >
      <h2>{mode === 'create' ? 'Crear paciente ficticio' : `Editar ${patient?.internal_code}`}</h2>

      {formError && <p role="alert">{formError}</p>}

      <div>
        <label htmlFor="internal_code">Código interno *</label>
        <input
          id="internal_code"
          value={internalCode}
          onChange={(event) => setInternalCode(event.target.value)}
          required
          maxLength={64}
          aria-invalid={Boolean(fieldErrors.internal_code)}
          aria-describedby={fieldErrors.internal_code ? 'internal_code-error' : undefined}
        />
        {fieldErrors.internal_code && (
          <p id="internal_code-error" role="alert">
            {fieldErrors.internal_code}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="display_name">Nombre para mostrar</label>
        <input
          id="display_name"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          maxLength={200}
          aria-invalid={Boolean(fieldErrors.display_name)}
          aria-describedby={fieldErrors.display_name ? 'display_name-error' : undefined}
        />
        {fieldErrors.display_name && (
          <p id="display_name-error" role="alert">
            {fieldErrors.display_name}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="birth_year">Año de nacimiento</label>
        <input
          id="birth_year"
          type="number"
          value={birthYear}
          onChange={(event) => setBirthYear(event.target.value)}
          aria-invalid={Boolean(fieldErrors.birth_year)}
          aria-describedby={fieldErrors.birth_year ? 'birth_year-error' : undefined}
        />
        {fieldErrors.birth_year && (
          <p id="birth_year-error" role="alert">
            {fieldErrors.birth_year}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="sex">Sexo (administrativo)</label>
        <select id="sex" value={sex} onChange={(event) => setSex(event.target.value as Sex | '')}>
          <option value="">Sin especificar</option>
          {SEX_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="notes">Notas administrativas</label>
        <textarea
          id="notes"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          maxLength={2000}
          aria-invalid={Boolean(fieldErrors.notes)}
          aria-describedby={fieldErrors.notes ? 'notes-error' : undefined}
        />
        {fieldErrors.notes && (
          <p id="notes-error" role="alert">
            {fieldErrors.notes}
          </p>
        )}
      </div>

      <div>
        <button type="submit" disabled={submitting}>
          {mode === 'create' ? 'Crear paciente' : 'Guardar cambios'}
        </button>
        <button type="button" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
      </div>
    </form>
  )
}
