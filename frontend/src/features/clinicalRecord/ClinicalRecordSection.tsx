import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
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
 * `ClinicalRecordExportActions`. La página (`offset`) vive en el query
 * param de la URL: permite compartir/recargar en una página concreta. */
export function ClinicalRecordSection({ devUserId, role, patient, professionalOptions }: Props) {
  const [searchParams, setSearchParams] = useSearchParams()
  const offset = Number(searchParams.get('offset') ?? '0') || 0
  const [page, setPage] = useState<ClinicalRecordPage | null>(null)
  const [state, setState] = useState<LoadState>('loading')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  function setOffset(next: number) {
    if (next === 0) {
      setSearchParams((params) => {
        params.delete('offset')
        return params
      })
    } else {
      setSearchParams((params) => {
        params.set('offset', String(next))
        return params
      })
    }
  }

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
