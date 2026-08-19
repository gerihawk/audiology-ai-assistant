import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AudioRecording } from '../../shared/api/types'
import { ExpiredAudioSection } from './ExpiredAudioSection'

function makeAudio(overrides: Partial<AudioRecording> = {}): AudioRecording {
  return {
    id: 'audio-1',
    clinical_session_id: 'session-1',
    status: 'ready',
    storage_provider: 'local',
    original_filename: 'consulta_ficticia.mp3',
    mime_type: 'audio/mpeg',
    extension: 'mp3',
    duration_seconds: 30,
    size_bytes: 1024,
    checksum: 'checksum',
    failure_reason: null,
    uploaded_by: 'u-1',
    uploaded_at: '2026-01-01T00:00:00Z',
    deleted_at: null,
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

describe('ExpiredAudioSection', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('no renderiza nada para un rol distinto de admin', () => {
    const { container } = render(<ExpiredAudioSection devUserId="u-viewer" role="viewer" />)
    expect(container).toBeEmptyDOMElement()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('lista el audio expirado para admin', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [makeAudio()] }))
    render(<ExpiredAudioSection devUserId="u-admin" role="admin" />)

    expect(await screen.findByText(/consulta_ficticia\.mp3/)).toBeInTheDocument()
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/retention/expired-audio')
  })

  it('muestra un mensaje cuando no hay audio expirado', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [] }))
    render(<ExpiredAudioSection devUserId="u-admin" role="admin" />)

    expect(
      await screen.findByText(/no hay audio que supere el periodo de retención/i),
    ).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /purgar audio expirado/i })).not.toBeInTheDocument()
  })

  it('pide confirmación antes de purgar y refresca la lista tras confirmar', async () => {
    fetchMock.mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return Promise.resolve(jsonResponse({ items: [makeAudio({ status: 'deleted' })] }))
      }
      return Promise.resolve(jsonResponse({ items: [makeAudio()] }))
    })
    const user = userEvent.setup()

    render(<ExpiredAudioSection devUserId="u-admin" role="admin" />)

    await user.click(await screen.findByRole('button', { name: /purgar audio expirado/i }))

    expect(window.confirm).toHaveBeenCalled()
    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(postCall).toBeDefined()
    })
  })

  it('no purga si el usuario cancela la confirmación', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    fetchMock.mockResolvedValue(jsonResponse({ items: [makeAudio()] }))
    const user = userEvent.setup()

    render(<ExpiredAudioSection devUserId="u-admin" role="admin" />)

    await user.click(await screen.findByRole('button', { name: /purgar audio expirado/i }))

    expect(fetchMock.mock.calls.every(([, init]) => init?.method !== 'POST')).toBe(true)
  })

  it('muestra el error del backend si falla la purga', async () => {
    fetchMock.mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return Promise.resolve(
          jsonResponse(
            { error: { code: 'forbidden', message: 'No autorizado.' } },
            { status: 403 },
          ),
        )
      }
      return Promise.resolve(jsonResponse({ items: [makeAudio()] }))
    })
    const user = userEvent.setup()

    render(<ExpiredAudioSection devUserId="u-admin" role="admin" />)

    await user.click(await screen.findByRole('button', { name: /purgar audio expirado/i }))

    expect(await screen.findByText(/no autorizado/i)).toBeInTheDocument()
  })
})
