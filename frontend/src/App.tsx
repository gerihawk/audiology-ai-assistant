import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { BackendStatus } from './shared/BackendStatus'
import { DevUserProvider } from './shared/devUser/DevUserContext'
import { DevUserSwitcher } from './shared/devUser/DevUserSwitcher'
import { NotFoundPage } from './shared/NotFoundPage'
import { ClinicalSessionsPage } from './features/clinicalSessions/ClinicalSessionsPage'
import { ClinicalSessionCreatePage } from './features/clinicalSessions/ClinicalSessionCreatePage'
import { ClinicalSessionDetailPage } from './features/clinicalSessions/ClinicalSessionDetailPage'
import { ClinicalSessionEditPage } from './features/clinicalSessions/ClinicalSessionEditPage'
import { PatientsPage } from './features/patients/PatientsPage'
import { PatientCreatePage } from './features/patients/PatientCreatePage'
import { PatientDetailPage } from './features/patients/PatientDetailPage'
import { PatientEditPage } from './features/patients/PatientEditPage'
import { PatientClinicalRecordPage } from './features/patients/PatientClinicalRecordPage'

function App() {
  return (
    <DevUserProvider>
      <main>
        <h1>Audiology AI Assistant</h1>
        <p>
          Nombre provisional del producto. Estado actual: Fase 3 (sesiones clínicas
          administrativas).
        </p>

        <BackendStatus />

        <section aria-label="Usuario de desarrollo">
          <h2>Usuario ficticio activo</h2>
          <DevUserSwitcher />
        </section>

        <nav aria-label="Secciones de la aplicación">
          <NavLink to="/patients">Pacientes</NavLink>
          <NavLink to="/clinical-sessions">Sesiones clínicas</NavLink>
        </nav>

        <Routes>
          <Route path="/" element={<Navigate to="/patients" replace />} />

          <Route
            path="/patients"
            element={
              <section>
                <h2>Pacientes ficticios</h2>
                <PatientsPage />
              </section>
            }
          />
          <Route path="/patients/new" element={<PatientCreatePage />} />
          <Route path="/patients/:patientId" element={<PatientDetailPage />} />
          <Route path="/patients/:patientId/edit" element={<PatientEditPage />} />
          <Route
            path="/patients/:patientId/clinical-record"
            element={<PatientClinicalRecordPage />}
          />

          <Route
            path="/clinical-sessions"
            element={
              <section>
                <h2>Sesiones clínicas ficticias</h2>
                <ClinicalSessionsPage />
              </section>
            }
          />
          <Route path="/clinical-sessions/new" element={<ClinicalSessionCreatePage />} />
          <Route path="/clinical-sessions/:sessionId" element={<ClinicalSessionDetailPage />} />
          <Route
            path="/clinical-sessions/:sessionId/ai-artifacts/:artifactId"
            element={<ClinicalSessionDetailPage />}
          />
          <Route path="/clinical-sessions/:sessionId/edit" element={<ClinicalSessionEditPage />} />

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
    </DevUserProvider>
  )
}

export default App
