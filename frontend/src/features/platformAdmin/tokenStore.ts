/** Almacén del JWT del operador de la plataforma (Fase 14) — mismo patrón
 * que `shared/auth/tokenStore.ts` (variable de módulo + pub/sub +
 * `sessionStorage`), pero deliberadamente un módulo aparte con su propia
 * clave de `sessionStorage`: el token de operador de plataforma y el
 * token de usuario de clínica son dos identidades completamente
 * independientes (ver `backend/app/platform_admin/service.py`) y no deben
 * compartir almacén — mezclarlos aquí sería el mismo error, en el
 * frontend, que el backend evita con el claim `typ` del JWT.
 *
 * `sessionStorage`, no `localStorage`, mismo motivo que el token de
 * clínica: la sesión no debe sobrevivir más allá de la pestaña/ventana
 * actual — más importante todavía aquí, es una identidad de más
 * privilegio (puede desactivar cualquier clínica de la plataforma). */

const STORAGE_KEY = 'audiology.platformAuthToken'

function readStoredToken(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

let token: string | null = readStoredToken()

const listeners = new Set<() => void>()

function notify(): void {
  for (const listener of listeners) listener()
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function getPlatformToken(): string | null {
  return token
}

export function setPlatformToken(newToken: string): void {
  token = newToken
  try {
    sessionStorage.setItem(STORAGE_KEY, newToken)
  } catch {
    // sessionStorage no disponible (p. ej. modo privado); el token sigue
    // en memoria para el resto de esta carga de página.
  }
  notify()
}

export function clearPlatformToken(): void {
  token = null
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // no-op, ver setPlatformToken.
  }
  notify()
}
