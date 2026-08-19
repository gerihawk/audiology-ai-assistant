import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { BackendStatus } from './shared/BackendStatus'
import { AuthProvider, useAuth } from './shared/auth/AuthContext'
import { LoginForm } from './shared/auth/LoginForm'
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
import { RetentionPage } from './features/retention/RetentionPage'
import { IntegrationsPage } from './features/integrations/IntegrationsPage'

/** Cabecera compartida por los dos modos de autenticación (Fase 9, hito
 * 9.2) — extraída para que fake/real no puedan divergir accidentalmente. */
function AppHeader() {
  return (
    <>
      <h1>Audiology AI Assistant</h1>
      <p>
        Nombre provisional del producto. Estado actual: Fase 3 (sesiones clínicas administrativas).
      </p>

      <BackendStatus />
    </>
  )
}

/** Idéntica en los dos modos — ver `AppHeader`. */
function AppNav() {
  return (
    <nav aria-label="Secciones de la aplicación">
      <NavLink to="/patients">Pacientes</NavLink>
      <NavLink to="/clinical-sessions">Sesiones clínicas</NavLink>
      <NavLink to="/retention">Retención</NavLink>
      <NavLink to="/integrations">Integraciones</NavLink>
    </nav>
  )
}

/** Misma lista de rutas en los dos modos de autenticación — solo lo que
 * envuelve a `<AppRoutes />` cambia entre `VITE_AUTH_MODE=fake|real`. */
function AppRoutes() {
  return (
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
      <Route path="/patients/:patientId/clinical-record" element={<PatientClinicalRecordPage />} />

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

      <Route path="/retention" element={<RetentionPage />} />
      <Route path="/integrations" element={<IntegrationsPage />} />

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}

/** `VITE_AUTH_MODE=fake` (por defecto): comportamiento idéntico al de
 * antes de la Fase 9 — `X-Dev-User-Id` vía `DevUserSwitcher`. */
function FakeAuthApp() {
  return (
    <DevUserProvider>
      <main>
        <AppHeader />

        <section aria-label="Usuario de desarrollo">
          <h2>Usuario ficticio activo</h2>
          <DevUserSwitcher />
        </section>

        <AppNav />
        <AppRoutes />
      </main>
    </DevUserProvider>
  )
}

/** `VITE_AUTH_MODE=real` (Fase 9, hito 9.2): sin token válido, pantalla
 * de login; con él, mismo contenido que `FakeAuthApp` (misma `AppNav`/
 * `AppRoutes`) más un botón de logout donde antes vivía el selector de
 * usuario ficticio. */
function RealAuthApp() {
  const { status, currentUser, errorMessage, signOut } = useAuth()

  return (
    <main>
      <AppHeader />

      {status === 'authenticated' && currentUser ? (
        <>
          <section aria-label="Sesión">
            <p data-testid="current-user-summary">
              Sesión iniciada como <strong>{currentUser.display_name}</strong> ({currentUser.email})
            </p>
            <button type="button" onClick={signOut}>
              Cerrar sesión
            </button>
          </section>

          <AppNav />
          <AppRoutes />
        </>
      ) : (
        <section aria-label="Autenticación">
          {status === 'checking' && <p role="status">Comprobando sesión…</p>}
          <LoginForm />
          {status === 'unauthenticated' && errorMessage && <p role="alert">{errorMessage}</p>}
        </section>
      )}
    </main>
  )
}

function App() {
  const isRealAuthMode = import.meta.env.VITE_AUTH_MODE === 'real'

  if (isRealAuthMode) {
    return (
      <AuthProvider>
        <RealAuthApp />
      </AuthProvider>
    )
  }
  return <FakeAuthApp />
}

export default App
