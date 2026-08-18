import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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

    // El tamaño exacto en bytes depende de la fidelidad del polyfill
    // Blob/Response de jsdom (entorno de test), no de `apiDownload` — lo
    // relevante aquí es que llega un Blob con contenido real y que el
    // filename se toma de Content-Disposition, nunca se reconstruye.
    expect(result.blob).toBeInstanceOf(Blob)
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
