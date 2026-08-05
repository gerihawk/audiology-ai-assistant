import { describe, expect, it } from 'vitest'
import type { ClinicalSession } from '../../shared/api/types'
import {
  canArchive,
  canCancel,
  canChangeProfessional,
  canComplete,
  canCreateSession,
  canReview,
  canRestore,
  canStart,
  canSubmitReview,
  canUpdateMetadata,
  editableFieldsForStatus,
} from './permissions'

function makeSession(overrides: Partial<ClinicalSession> = {}): ClinicalSession {
  return {
    id: 's-1',
    clinic_id: 'c-1',
    patient_id: 'p-1',
    professional_id: 'u-audiologist',
    session_type: 'initial_assessment',
    status: 'scheduled',
    scheduled_at: null,
    started_at: null,
    ended_at: null,
    title: null,
    administrative_notes: null,
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

describe('permisos de clinical_sessions', () => {
  it('admin y audiologist pueden crear sesiones; viewer no', () => {
    expect(canCreateSession('admin')).toBe(true)
    expect(canCreateSession('audiologist')).toBe(true)
    expect(canCreateSession('viewer')).toBe(false)
    expect(canCreateSession(undefined)).toBe(false)
  })

  it('un audiologist solo puede actuar sobre sus propias sesiones', () => {
    const ownSession = makeSession({ professional_id: 'u-audiologist' })
    const otherSession = makeSession({ professional_id: 'u-other' })

    expect(canUpdateMetadata('audiologist', ownSession, 'u-audiologist')).toBe(true)
    expect(canUpdateMetadata('audiologist', otherSession, 'u-audiologist')).toBe(false)
    expect(canStart('audiologist', otherSession, 'u-audiologist')).toBe(false)
    expect(canCancel('audiologist', otherSession, 'u-audiologist')).toBe(false)
  })

  it('un admin puede actuar sobre cualquier sesión de su clínica', () => {
    const otherSession = makeSession({ professional_id: 'u-other', status: 'in_progress' })
    expect(canComplete('admin', otherSession, 'u-admin')).toBe(true)
    expect(canCancel('admin', otherSession, 'u-admin')).toBe(true)
  })

  it('un viewer nunca puede actuar sobre sesiones', () => {
    const session = makeSession()
    expect(canUpdateMetadata('viewer', session, 'u-audiologist')).toBe(false)
    expect(canStart('viewer', session, 'u-audiologist')).toBe(false)
  })

  it('solo permite cambiar el profesional responsable a un admin', () => {
    expect(canChangeProfessional('admin')).toBe(true)
    expect(canChangeProfessional('audiologist')).toBe(false)
    expect(canChangeProfessional('viewer')).toBe(false)
  })

  it('start/complete/submit-review solo son válidos en el estado previo correcto', () => {
    const scheduled = makeSession({ status: 'scheduled' })
    const inProgress = makeSession({ status: 'in_progress' })
    const completed = makeSession({ status: 'completed' })

    expect(canStart('admin', scheduled, 'u-admin')).toBe(true)
    expect(canStart('admin', inProgress, 'u-admin')).toBe(false)

    expect(canComplete('admin', inProgress, 'u-admin')).toBe(true)
    expect(canComplete('admin', scheduled, 'u-admin')).toBe(false)

    expect(canSubmitReview('admin', completed, 'u-admin')).toBe(true)
    expect(canSubmitReview('admin', inProgress, 'u-admin')).toBe(false)
  })

  it('review solo está disponible para admin y solo en review_pending', () => {
    const reviewPending = makeSession({ status: 'review_pending' })
    const completed = makeSession({ status: 'completed' })

    expect(canReview('admin', reviewPending)).toBe(true)
    expect(canReview('audiologist', reviewPending)).toBe(false)
    expect(canReview('admin', completed)).toBe(false)
  })

  it('cancel solo es válido desde scheduled o in_progress y nunca si está archivada', () => {
    expect(canCancel('admin', makeSession({ status: 'scheduled' }), 'u-admin')).toBe(true)
    expect(canCancel('admin', makeSession({ status: 'in_progress' }), 'u-admin')).toBe(true)
    expect(canCancel('admin', makeSession({ status: 'completed' }), 'u-admin')).toBe(false)
    expect(
      canCancel('admin', makeSession({ status: 'scheduled', is_archived: true }), 'u-admin'),
    ).toBe(false)
  })

  it('archive solo es válido desde completed/reviewed/cancelled y nunca si ya está archivada', () => {
    expect(canArchive('admin', makeSession({ status: 'completed' }), 'u-admin')).toBe(true)
    expect(canArchive('admin', makeSession({ status: 'reviewed' }), 'u-admin')).toBe(true)
    expect(canArchive('admin', makeSession({ status: 'cancelled' }), 'u-admin')).toBe(true)
    expect(canArchive('admin', makeSession({ status: 'review_pending' }), 'u-admin')).toBe(false)
    expect(
      canArchive('admin', makeSession({ status: 'completed', is_archived: true }), 'u-admin'),
    ).toBe(false)
  })

  it('restore solo está disponible para admin y solo si la sesión está archivada', () => {
    expect(canRestore('admin', makeSession({ is_archived: true }))).toBe(true)
    expect(canRestore('admin', makeSession({ is_archived: false }))).toBe(false)
    expect(canRestore('audiologist', makeSession({ is_archived: true }))).toBe(false)
  })

  it('editableFieldsForStatus refleja las reglas de edición por estado', () => {
    expect(editableFieldsForStatus('scheduled')).toBe('all')
    expect(editableFieldsForStatus('in_progress')).toBe('all')
    expect(editableFieldsForStatus('completed')).toBe('all')
    expect(editableFieldsForStatus('review_pending')).toBe('restricted')
    expect(editableFieldsForStatus('reviewed')).toBe('none')
    expect(editableFieldsForStatus('cancelled')).toBe('none')
  })
})
