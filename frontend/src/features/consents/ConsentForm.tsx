import { useState } from 'react'
import type { FormEvent } from 'react'
import { createConsent } from '../../shared/api/consents'
import type { Consent, ConsentType } from '../../shared/api/types'
import { describeActionError } from '../../shared/apiErrorMessage'
import { CONSENT_TYPE_LABELS, CONSENT_TYPES } from './labels'

interface Props {
  devUserId: string
  patientId: string
  onDone: (consent: Consent) => void
  onCancel: () => void
}

export function ConsentForm({ devUserId, patientId, onDone, onCancel }: Props) {
  const [consentType, setConsentType] = useState<ConsentType>('procesamiento_ia')
  const [granted, setGranted] = useState(true)
  const [notes, setNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) return
    setSubmitting(true)
    setFormError(null)
    try {
      const result = await createConsent(devUserId, patientId, {
        consent_type: consentType,
        granted,
        notes: notes || null,
      })
      onDone(result)
    } catch (error) {
      const described = describeActionError(error)
      setFormError(`${described.label}: ${described.message}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} aria-label="Registrar consentimiento">
      <h4>Registrar consentimiento</h4>
      {formError && <p role="alert">{formError}</p>}

      <div>
        <label htmlFor="consent-type">Tipo *</label>
        <select
          id="consent-type"
          value={consentType}
          onChange={(event) => setConsentType(event.target.value as ConsentType)}
        >
          {CONSENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {CONSENT_TYPE_LABELS[type]}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor="consent-granted">
          <input
            id="consent-granted"
            type="checkbox"
            checked={granted}
            onChange={(event) => setGranted(event.target.checked)}
          />
          Otorgado
        </label>
      </div>

      <div>
        <label htmlFor="consent-notes">Notas (opcional)</label>
        <textarea
          id="consent-notes"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          maxLength={2000}
        />
      </div>

      <div>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Guardando…' : 'Registrar'}
        </button>
        <button type="button" onClick={onCancel} disabled={submitting}>
          Cancelar
        </button>
      </div>
    </form>
  )
}
