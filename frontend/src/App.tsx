import { BackendStatus } from './shared/BackendStatus'
import { DevUserProvider } from './shared/devUser/DevUserContext'
import { DevUserSwitcher } from './shared/devUser/DevUserSwitcher'
import { PatientsPage } from './features/patients/PatientsPage'

function App() {
  return (
    <DevUserProvider>
      <main>
        <h1>Audiology AI Assistant</h1>
        <p>
          Nombre provisional del producto. Estado actual: Fase 2 (clínicas, usuarios, pacientes).
        </p>

        <BackendStatus />

        <section aria-label="Usuario de desarrollo">
          <h2>Usuario ficticio activo</h2>
          <DevUserSwitcher />
        </section>

        <section>
          <h2>Pacientes ficticios</h2>
          <PatientsPage />
        </section>
      </main>
    </DevUserProvider>
  )
}

export default App
