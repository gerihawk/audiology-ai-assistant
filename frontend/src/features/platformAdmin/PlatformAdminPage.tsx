import { PlatformAuthProvider, usePlatformAuth } from './PlatformAuthContext'
import { PlatformClinicsPanel } from './PlatformClinicsPanel'
import { PlatformLoginForm } from './PlatformLoginForm'

/** Contenido de `/platform` una vez dentro de `<PlatformAuthProvider>` —
 * mismo papel que `RealAuthApp` en `App.tsx`, pero para el mundo del
 * operador de plataforma: sin token válido, formulario de login; con él,
 * el panel de clínicas y un botón de logout. */
function PlatformAdminContent() {
  const { status, operator, errorMessage, signOut } = usePlatformAuth()

  return (
    <main>
      <h1>Panel de operador de la plataforma</h1>
      <p>
        Acceso restringido — identidad completamente separada de las clínicas y sus usuarios (ver
        docs/development-plan.md, Fase 14).
      </p>

      {status === 'authenticated' && operator ? (
        <>
          <section aria-label="Sesión de operador">
            <p data-testid="platform-operator-summary">
              Conectado como <strong>{operator.display_name}</strong> ({operator.email})
            </p>
            <button type="button" onClick={signOut}>
              Cerrar sesión
            </button>
          </section>

          <PlatformClinicsPanel />
        </>
      ) : (
        <section aria-label="Autenticación de operador">
          {status === 'checking' && <p role="status">Comprobando sesión…</p>}
          <PlatformLoginForm />
          {status === 'unauthenticated' && errorMessage && <p role="alert">{errorMessage}</p>}
        </section>
      )}
    </main>
  )
}

/** Elemento de ruta para `/platform` (App.tsx) — colocado en el `<Routes>`
 * exterior, independiente de `VITE_AUTH_MODE`/`FakeAuthApp`/`RealAuthApp`:
 * el operador de plataforma no es un usuario de ninguna clínica, así que
 * no tiene sentido que su acceso dependa del modo de autenticación de
 * usuarios de clínica (ver `backend/app/platform_admin/service.py`). */
export function PlatformAdminPage() {
  return (
    <PlatformAuthProvider>
      <PlatformAdminContent />
    </PlatformAuthProvider>
  )
}
