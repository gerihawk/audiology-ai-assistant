import type { DevUser } from '../../shared/api/types'

export function formatDateTime(isoValue: string | null): string {
  if (!isoValue) return '—'
  const parsed = new Date(isoValue)
  if (Number.isNaN(parsed.getTime())) return isoValue
  return parsed.toLocaleString('es-ES', {
    dateStyle: 'short',
    timeStyle: 'short',
  })
}

export function professionalName(professionalId: string, professionalOptions: DevUser[]): string {
  return (
    professionalOptions.find((user) => user.id === professionalId)?.display_name ?? professionalId
  )
}
