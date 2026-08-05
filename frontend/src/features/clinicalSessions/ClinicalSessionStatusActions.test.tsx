import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ClinicalSession } from '../../shared/api/types'
import { ClinicalSessionStatusActions } from './ClinicalSessionStatusActions'

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

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

describe('ClinicalSessionStatusActions', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('permite iniciar una sesión scheduled propia (transición válida)', async () => {
    const session = makeSession({ status: 'scheduled' })
    fetchMock.mockResolvedValue(jsonResponse({ ...session, status: 'in_progress' }))
    const onChanged = vi.fn()
    const user = userEvent.setup()

    render(
      <ClinicalSessionStatusActions
        devUserId="u-audiologist"
        role="audiologist"
        currentUserId="u-audiologist"
        session={session}
        onChanged={onChanged}
      />,
    )

    const startButton = screen.getByRole('button', { name: /iniciar/i })
    await user.click(startButton)

    await waitFor(() =>
      expect(onChanged).toHaveBeenCalledWith({ ...session, status: 'in_progress' }),
    )
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/clinical-sessions/s-1/start'),
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('no ofrece "Completar" sobre una sesión scheduled (transición inválida)', () => {
    const session = makeSession({ status: 'scheduled' })
    render(
      <ClinicalSessionStatusActions
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        session={session}
        onChanged={vi.fn()}
      />,
    )

    expect(screen.queryByRole('button', { name: /^completar$/i })).not.toBeInTheDocument()
  })

  it('un audiologist no ve acciones sobre una sesión de otro profesional', () => {
    const session = makeSession({ status: 'scheduled', professional_id: 'u-otro' })
    const { container } = render(
      <ClinicalSessionStatusActions
        devUserId="u-audiologist"
        role="audiologist"
        currentUserId="u-audiologist"
        session={session}
        onChanged={vi.fn()}
      />,
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('"Marcar como revisada" solo se muestra a un admin en review_pending', () => {
    const session = makeSession({ status: 'review_pending', professional_id: 'u-audiologist' })

    const { rerender } = render(
      <ClinicalSessionStatusActions
        devUserId="u-audiologist"
        role="audiologist"
        currentUserId="u-audiologist"
        session={session}
        onChanged={vi.fn()}
      />,
    )
    expect(screen.queryByRole('button', { name: /marcar como revisada/i })).not.toBeInTheDocument()

    rerender(
      <ClinicalSessionStatusActions
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        session={session}
        onChanged={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: /marcar como revisada/i })).toBeInTheDocument()
  })

  it('pide confirmación antes de cancelar y llama a la API si se confirma', async () => {
    const session = makeSession({ status: 'scheduled' })
    fetchMock.mockResolvedValue(jsonResponse({ ...session, status: 'cancelled' }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()

    render(
      <ClinicalSessionStatusActions
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        session={session}
        onChanged={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /cancelar/i }))

    expect(window.confirm).toHaveBeenCalled()
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/cancel'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('no llama a la API de cancelar si el usuario rechaza la confirmación', async () => {
    const session = makeSession({ status: 'scheduled' })
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()

    render(
      <ClinicalSessionStatusActions
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        session={session}
        onChanged={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /cancelar/i }))

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('archiva una sesión completed tras confirmar', async () => {
    const session = makeSession({ status: 'completed' })
    fetchMock.mockResolvedValue(jsonResponse({ ...session, is_archived: true }))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()

    render(
      <ClinicalSessionStatusActions
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        session={session}
        onChanged={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /archivar/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/archive'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('restaura una sesión archivada (solo admin)', async () => {
    const session = makeSession({ status: 'completed', is_archived: true })
    fetchMock.mockResolvedValue(jsonResponse({ ...session, is_archived: false }))
    const user = userEvent.setup()

    render(
      <ClinicalSessionStatusActions
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        session={session}
        onChanged={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: /restaurar/i }))

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/restore'),
        expect.objectContaining({ method: 'POST' }),
      )
    })
  })

  it('bloquea el doble envío mientras una acción está en curso', async () => {
    const session = makeSession({ status: 'scheduled' })
    let resolveFetch: (value: Response) => void = () => {}
    fetchMock.mockReturnValue(
      new Promise((resolve) => {
        resolveFetch = resolve
      }),
    )
    const user = userEvent.setup()

    render(
      <ClinicalSessionStatusActions
        devUserId="u-admin"
        role="admin"
        currentUserId="u-admin"
        session={session}
        onChanged={vi.fn()}
      />,
    )

    const startButton = screen.getByRole('button', { name: /iniciar/i })
    await user.click(startButton)
    await user.click(startButton)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    resolveFetch(jsonResponse({ ...session, status: 'in_progress' }))
  })
})
