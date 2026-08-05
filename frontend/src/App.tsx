import { useState } from 'react'
import { BackendStatus } from './shared/BackendStatus'
import { DevUserProvider } from './shared/devUser/DevUserContext'
import { DevUserSwitcher } from './shared/devUser/DevUserSwitcher'
import { ClinicalSessionsPage } from './features/clinicalSessions/ClinicalSessionsPage'
import { PatientsPage } from './features/patients/PatientsPage'

type Tab = 'patients' | 'clinicalSessions'

function App() {
  const [tab, setTab] = useState<Tab>('patients')

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
          <button
            type="button"
            aria-current={tab === 'patients' ? 'page' : undefined}
            onClick={() => setTab('patients')}
          >
            Pacientes
          </button>
          <button
            type="button"
            aria-current={tab === 'clinicalSessions' ? 'page' : undefined}
            onClick={() => setTab('clinicalSessions')}
          >
            Sesiones clínicas
          </button>
        </nav>

        {tab === 'patients' && (
          <section>
            <h2>Pacientes ficticios</h2>
            <PatientsPage />
          </section>
        )}

        {tab === 'clinicalSessions' && (
          <section>
            <h2>Sesiones clínicas ficticias</h2>
            <ClinicalSessionsPage />
          </section>
        )}
      </main>
    </DevUserProvider>
  )
}

export default App
