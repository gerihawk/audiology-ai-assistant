import { useCallback, useEffect, useState } from 'react'
import { AIDisclaimer } from '../aiPipeline/AIDisclaimer'
import { getClinicalRecord } from '../../shared/api/clinicalRecord'
import type { ClinicalRecordPage, DevUser, Patient, Role } from '../../shared/api/types'
import { canReadClinicalRecord } from '../../shared/clinicalDocumentPermissions'
import { ClinicalRecordExportActions } from './ClinicalRecordExportActions'
import { ClinicalRecordSessionCard } from './ClinicalRecordSessionCard'

const PAGE_SIZE = 10

type LoadState = 'loading' | 'ready' | 'error'

interface Props {
  devUserId: string
  role: Role | undefined
  patient: Patient
  professionalOptions: DevUser[]
}

/** `GET /patients/{id}/clinical-record` — vista de solo lectura,
 * paginada por sesiones (no por documentos), en el orden recibido del
 * backend. `viewer` puede leer esta sección igual que admin/audiologist
 * (`ClinicalRecordAction.READ` sin ownership) pero no exportar — ver
 * `ClinicalRecordExportActions`. */
export function ClinicalRecordSection({ devUserId, role, patient, professionalOptions }: Props) {
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<ClinicalRecordPage | null>(null)
  const [state, setState] = useState<LoadState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const load = useCallback(() => {
    setState('loading')
    setErrorMessage(null)
    getClinicalRecord(devUserId, patient.id, { limit: PAGE_SIZE, offset })
      .then((response) => {
        setPage(response)
        setState('ready')
      })
      .catch((error: unknown) => {
        setErrorMessage(
          error instanceof Error ? error.message : 'No se pudo cargar la historia clínica.',
        )
        setState('error')
      })
  }, [devUserId, patient.id, offset])

  useEffect(() => {
    load()
  }, [load])

  if (!canReadClinicalRecord(role)) return null

  return (
    <section aria-label="Historia clínica longitudinal">
      <h3>Historia clínica</h3>

      {state === 'loading' && <p role="status">Cargando historia clínica…</p>}
      {state === 'error' && <p role="alert">Error al cargar la historia clínica: {errorMessage}</p>}

      {state === 'ready' && page && (
        <>
          <AIDisclaimer text={page.ai_disclaimer} />

          <ClinicalRecordExportActions
            devUserId={devUserId}
            role={role}
            patientId={patient.id}
            limit={page.limit}
            offset={page.offset}
          />

          {page.sessions.length === 0 ? (
            <p>El paciente no tiene sesiones registradas en la historia clínica.</p>
          ) : (
            <ul className="clinical-record-sessions" aria-label="Sesiones de la historia clínica">
              {page.sessions.map((session) => (
                <ClinicalRecordSessionCard
                  key={session.clinical_session_id}
                  session={session}
                  professionalOptions={professionalOptions}
                />
              ))}
            </ul>
          )}

          {page.total > PAGE_SIZE && (
            <nav aria-label="Paginación de la historia clínica">
              <button
                type="button"
                disabled={page.offset === 0}
                onClick={() => setOffset(Math.max(0, page.offset - PAGE_SIZE))}
              >
                Anterior
              </button>
              <span>
                {page.offset + 1}–{Math.min(page.offset + PAGE_SIZE, page.total)} de {page.total}
              </span>
              <button
                type="button"
                disabled={page.offset + PAGE_SIZE >= page.total}
                onClick={() => setOffset(page.offset + PAGE_SIZE)}
              >
                Siguiente
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  )
}
