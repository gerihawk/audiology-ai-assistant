import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClinicalSession, DevUser } from '../../shared/api/types'
import { ClinicalSessionDetail } from './ClinicalSessionDetail'

function makeSession(overrides: Partial<ClinicalSession> = {}): ClinicalSession {
  return {
    id: 's-1',
    clinic_id: 'c-1',
    patient_id: 'p-1',
    professional_id: 'u-audiologist',
    session_type: 'follow_up',
    status: 'completed',
    scheduled_at: '2026-02-10T09:00:00Z',
    started_at: '2026-02-10T09:05:00Z',
    ended_at: '2026-02-10T09:40:00Z',
    title: 'Seguimiento trimestral',
    administrative_notes: 'Paciente puntual.',
    reviewed_by: null,
    reviewed_at: null,
    created_by: 'u-admin',
    updated_by: 'u-admin',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    schema_version: 1,
    is_archived: false,
    archived_at: null,
    ...overrides,
  }
}

const PROFESSIONALS: DevUser[] = [
  { id: 'u-audiologist', clinic_id: 'c-1', display_name: 'Ana Audióloga', role: 'audiologist' },
  { id: 'u-admin', clinic_id: 'c-1', display_name: 'Alberto Admin', role: 'admin' },
]

describe('ClinicalSessionDetail', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('muestra scheduled_at, started_at y ended_at', () => {
    const session = makeSession()
    render(
      <ClinicalSessionDetail
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        session={session}
        professionalOptions={PROFESSIONALS}
        onBack={vi.fn()}
        onEdit={vi.fn()}
        onChanged={vi.fn()}
      />,
    )

    expect(screen.getByText('Programada').nextElementSibling).toBeTruthy()
    expect(screen.getAllByText(/10\/2\/26/).length).toBeGreaterThanOrEqual(3)
  })

  it('muestra reviewed_by y reviewed_at solo cuando existen', () => {
    const reviewed = makeSession({
      status: 'reviewed',
      reviewed_by: 'u-admin',
      reviewed_at: '2026-02-11T10:00:00Z',
    })
    const { rerender } = render(
      <ClinicalSessionDetail
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        session={reviewed}
        professionalOptions={PROFESSIONALS}
        onBack={vi.fn()}
        onEdit={vi.fn()}
        onChanged={vi.fn()}
      />,
    )
    expect(screen.getByText('Revisada por')).toBeInTheDocument()
    expect(screen.getByText('Alberto Admin')).toBeInTheDocument()

    rerender(
      <ClinicalSessionDetail
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        session={makeSession({ reviewed_by: null, reviewed_at: null })}
        professionalOptions={PROFESSIONALS}
        onBack={vi.fn()}
        onEdit={vi.fn()}
        onChanged={vi.fn()}
      />,
    )
    expect(screen.queryByText('Revisada por')).not.toBeInTheDocument()
  })

  it('muestra el profesional responsable con nombre legible', () => {
    render(
      <ClinicalSessionDetail
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        session={makeSession()}
        professionalOptions={PROFESSIONALS}
        onBack={vi.fn()}
        onEdit={vi.fn()}
        onChanged={vi.fn()}
      />,
    )
    expect(screen.getByText('Ana Audióloga')).toBeInTheDocument()
  })

  it('muestra el botón de editar cuando el rol y el estado lo permiten', () => {
    render(
      <ClinicalSessionDetail
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        session={makeSession({ status: 'scheduled' })}
        professionalOptions={PROFESSIONALS}
        onBack={vi.fn()}
        onEdit={vi.fn()}
        onChanged={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /editar metadatos/i })).toBeInTheDocument()
  })

  it('oculta el botón de editar para una sesión reviewed', () => {
    render(
      <ClinicalSessionDetail
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        session={makeSession({ status: 'reviewed' })}
        professionalOptions={PROFESSIONALS}
        onBack={vi.fn()}
        onEdit={vi.fn()}
        onChanged={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /editar metadatos/i })).not.toBeInTheDocument()
  })

  it('oculta el botón de editar para un audiologist sobre una sesión ajena', () => {
    render(
      <ClinicalSessionDetail
        devUserId="u-audiologist"
        role="audiologist"
        currentUserId="u-audiologist"
        session={makeSession({ status: 'scheduled', professional_id: 'u-otro' })}
        professionalOptions={PROFESSIONALS}
        onBack={vi.fn()}
        onEdit={vi.fn()}
        onChanged={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /editar metadatos/i })).not.toBeInTheDocument()
  })
})
