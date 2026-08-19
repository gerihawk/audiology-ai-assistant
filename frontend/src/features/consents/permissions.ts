import type { Role } from '../../shared/api/types'

// Refleja core/authorization.py::CONSENT_PERMISSIONS (backend) — el
// backend es la autoridad real, esto solo evita mostrar acciones que el
// servidor rechazaría. Deliberadamente distinto del patrón "admin sin
// restricción": registrar un consentimiento es un acto asistencial ante
// el paciente, solo `audiologist` puede hacerlo; `admin` solo lee.

export function canReadConsents(role: Role | undefined): boolean {
  return role === 'admin' || role === 'audiologist'
}

export function canCreateConsent(role: Role | undefined): boolean {
  return role === 'audiologist'
}
