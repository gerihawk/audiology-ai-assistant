/** Almacén del JWT de autenticación real (Fase 9, hito 9.2) — variable de
 * módulo, no Context: `client.ts` no es un componente React y necesita
 * leerlo desde fuera del árbol de componentes en cada `apiRequest`.
 * `AuthContext` (estado de React) lee del mismo almacén.
 *
 * Persistido en `sessionStorage` (clave propia, distinta de
 * `audiology.devUserId`) para sobrevivir a un refresh de página dentro de
 * la misma pestaña — nunca `localStorage`: la sesión no debe sobrevivir
 * más allá de la pestaña/ventana actual. */

const STORAGE_KEY = 'audiology.authToken'

function readStoredToken(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

let token: string | null = readStoredToken()

export function getToken(): string | null {
  return token
}

export function setToken(newToken: string): void {
  token = newToken
  try {
    sessionStorage.setItem(STORAGE_KEY, newToken)
  } catch {
    // sessionStorage no disponible (p. ej. modo privado); el token sigue
    // en memoria para el resto de esta carga de página.
  }
}

export function clearToken(): void {
  token = null
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // no-op, ver setToken.
  }
}
