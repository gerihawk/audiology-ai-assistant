import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearToken, getToken, setToken } from '../auth/tokenStore'
import { ApiError, apiDownload, apiRequest } from './client'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function binaryResponse(byteValues: number[], init: ResponseInit = {}) {
  return new Response(new Blob([new Uint8Array(byteValues)]), {
    status: 200,
    headers: { 'content-type': 'application/pdf' },
    ...init,
  })
}

describe('apiRequest (regresión tras compartir parseErrorBody con apiDownload)', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sigue devolviendo el JSON de éxito', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))
    await expect(apiRequest('/x')).resolves.toEqual({ ok: true })
  })

  it('sigue lanzando ApiError con el cuerpo real en error', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ error: { code: 'not_found', message: 'x' } }, { status: 404 }),
    )
    await expect(apiRequest('/x')).rejects.toMatchObject({ status: 404, code: 'not_found' })
  })
})

describe('apiDownload', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reutiliza BASE_URL y envía X-Dev-User-Id, igual que apiRequest', async () => {
    fetchMock.mockResolvedValue(
      binaryResponse([1, 2, 3], {
        headers: {
          'content-type': 'application/pdf',
          'content-disposition': 'attachment; filename="doc.pdf"',
        },
      }),
    )

    await apiDownload('/api/v1/ai-artifacts/a-1/export?format=pdf', { devUserId: 'u-admin' })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('http://localhost:8000')
    expect(String(url)).toContain('/api/v1/ai-artifacts/a-1/export?format=pdf')
    expect(init.method).toBe('GET')
    expect(init.headers['X-Dev-User-Id']).toBe('u-admin')
  })

  it('devuelve el blob y el filename tomado de Content-Disposition, sin reconstruirlo', async () => {
    fetchMock.mockResolvedValue(
      binaryResponse([1, 2, 3], {
        headers: {
          'content-type': 'application/pdf',
          'content-disposition':
            'attachment; filename="paciente_p001_historia_clinica_20260101T000000Z.pdf"',
        },
      }),
    )

    const result = await apiDownload('/x', { devUserId: 'u-admin' })

    // `result.blob` viene de Response.prototype.blob() (undici/Node), que
    // vive en un realm distinto al `Blob` global que jsdom-environment
    // sustituye en este test — por eso `toBeInstanceOf(Blob)` falla pese a
    // tratarse de un Blob real. Verificamos el nombre del constructor en su
    // lugar; lo relevante sigue siendo que llega un Blob con contenido real
    // y que el filename se toma de Content-Disposition, nunca se reconstruye.
    expect(result.blob.constructor.name).toBe('Blob')
    expect(result.blob.size).toBeGreaterThan(0)
    expect(result.filename).toBe('paciente_p001_historia_clinica_20260101T000000Z.pdf')
  })

  it('filename es null si el backend no envía Content-Disposition (nunca se inventa uno)', async () => {
    fetchMock.mockResolvedValue(binaryResponse([1]))
    const result = await apiDownload('/x', { devUserId: 'u-admin' })
    expect(result.filename).toBeNull()
  })

  it('un error JSON del backend se convierte en ApiError, igual que en apiRequest', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'conflict', message: 'El artefacto no tiene una versión aprobada.' } },
        { status: 409 },
      ),
    )

    try {
      await apiDownload('/x', { devUserId: 'u-admin' })
      expect.fail('debía lanzar')
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      const apiError = error as ApiError
      expect(apiError.status).toBe(409)
      expect(apiError.code).toBe('conflict')
      expect(apiError.message).toBe('El artefacto no tiene una versión aprobada.')
    }
  })
})

describe('autenticación real (Fase 9, hito 9.2)', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    clearToken()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
    clearToken()
  })

  it('adjunta Authorization: Bearer cuando VITE_AUTH_MODE=real y hay token', async () => {
    vi.stubEnv('VITE_AUTH_MODE', 'real')
    setToken('token-abc')
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))

    await apiRequest('/api/v1/me')

    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers['Authorization']).toBe('Bearer token-abc')
  })

  it('no adjunta Authorization en VITE_AUTH_MODE=fake (por defecto), aunque haya token', async () => {
    setToken('token-abc')
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))

    await apiRequest('/api/v1/me')

    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers['Authorization']).toBeUndefined()
  })

  it('no adjunta Authorization en VITE_AUTH_MODE=real sin token', async () => {
    vi.stubEnv('VITE_AUTH_MODE', 'real')
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }))

    await apiRequest('/api/v1/me')

    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers['Authorization']).toBeUndefined()
  })

  it('limpia el token del almacén cuando el backend responde 401', async () => {
    vi.stubEnv('VITE_AUTH_MODE', 'real')
    setToken('token-abc')
    fetchMock.mockResolvedValue(
      jsonResponse(
        { error: { code: 'unauthenticated', message: 'Token inválido.' } },
        { status: 401 },
      ),
    )

    await expect(apiRequest('/api/v1/me')).rejects.toBeInstanceOf(ApiError)

    expect(getToken()).toBeNull()
  })

  it('apiDownload también adjunta Authorization: Bearer (misma ruta de autenticación)', async () => {
    vi.stubEnv('VITE_AUTH_MODE', 'real')
    setToken('token-abc')
    fetchMock.mockResolvedValue(binaryResponse([1]))

    await apiDownload('/x')

    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers['Authorization']).toBe('Bearer token-abc')
  })
})
