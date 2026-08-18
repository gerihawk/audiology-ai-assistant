import { Link, useParams } from 'react-router-dom'
import { useDevUser } from '../../shared/devUser/DevUserContext'
import { ClinicalRecordSection } from '../clinicalRecord/ClinicalRecordSection'
import { useProfessionalOptions } from '../clinicalSessions/useProfessionalOptions'
import { usePatient } from './usePatient'

export function PatientClinicalRecordPage() {
  const { patientId = '' } = useParams()
  const { currentUser, selectedUserId, status } = useDevUser()
  const professionalOptions = useProfessionalOptions(currentUser)
  const patientState = usePatient(selectedUserId ?? '', patientId)

  if (status === 'loading') {
    return <p role="status">Cargando…</p>
  }

  if (!selectedUserId) {
    return <p>Selecciona un usuario de desarrollo para gestionar pacientes.</p>
  }

  if (patientState.status === 'loading') {
    return <p role="status">Cargando paciente…</p>
  }

  if (patientState.status === 'error') {
    return <p role="alert">Error al cargar el paciente: {patientState.message}</p>
  }

  return (
    <div>
      <Link to={`/patients/${patientId}`}>Volver al paciente</Link>
      <h2>Historia clínica de {patientState.patient.internal_code}</h2>
      <ClinicalRecordSection
        devUserId={selectedUserId}
        role={currentUser?.role}
        patient={patientState.patient}
        professionalOptions={professionalOptions}
      />
    </div>
  )
}
