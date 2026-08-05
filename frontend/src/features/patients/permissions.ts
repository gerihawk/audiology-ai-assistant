import type { Role } from '../../shared/api/types'

// Refleja la matriz de core/authorization.py (backend). El backend es la
// autoridad real: esto solo evita mostrar acciones que el servidor
// rechazaría, para una mejor experiencia de uso.

export function canCreatePatient(role: Role | undefined): boolean {
  return role === 'admin' || role === 'audiologist'
}

export function canUpdatePatient(role: Role | undefined): boolean {
  return role === 'admin' || role === 'audiologist'
}

export function canArchivePatient(role: Role | undefined): boolean {
  return role === 'admin' || role === 'audiologist'
}

export function canRestorePatient(role: Role | undefined): boolean {
  return role === 'admin'
}
