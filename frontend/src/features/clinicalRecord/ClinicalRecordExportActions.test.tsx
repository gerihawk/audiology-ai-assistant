import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ClinicalRecordExportActions } from './ClinicalRecordExportActions'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init,
  })
}

function binaryResponse(init: ResponseInit = {}) {
  return new Response(new Blob([new Uint8Array([1, 2, 3])]), {
    status: 200,
    headers: { 'content-type': 'application/pdf' },
    ...init,
  })
}

describe('ClinicalRecordExportActions', () => {
  const fetchMock = vi.fn()
  const originalCreateObjectURL = URL.createObjectURL
  const originalRevokeObjectURL = URL.revokeObjectURL

  beforeEach(() => {
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    URL.createObjectURL = vi.fn(() => 'blob:mock-url')
    URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    URL.createObjectURL = originalCreateObjectURL
    URL.revokeObjectURL = originalRevokeObjectURL
  })

  it('un viewer nunca ve los botones de exportación (aunque pueda leer el Clinical Record)', () => {
    const { container } = render(
      <ClinicalRecordExportActions
        devUserId="u-viewer"
        role="viewer"
        patientId="p-1"
        limit={10}
        offset={0}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('admin/audiologist ven Exportar PDF y Exportar TXT', () => {
    render(
      <ClinicalRecordExportActions
        devUserId="u-admin"
        role="admin"
        patientId="p-1"
        limit={10}
        offset={0}
      />,
    )
    expect(screen.getByRole('button', { name: /exportar pdf/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /exportar txt/i })).toBeInTheDocument()
  })

  it('Exportar PDF llama al endpoint longitudinal con el limit/offset visible', async () => {
    fetchMock.mockResolvedValue(
      binaryResponse({
        headers: { 'content-disposition': 'attachment; filename="p001_historia_clinica_x.pdf"' },
      }),
    )
    const user = userEvent.setup()
    render(
      <ClinicalRecordExportActions
        devUserId="u-admin"
        role="admin"
        patientId="p-1"
        limit={10}
        offset={20}
      />,
    )

    await user.click(screen.getByRole('button', { name: /exportar pdf/i }))

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/v1/patients/p-1/clinical-record/export')
    expect(String(url)).toContain('format=pdf')
    expect(String(url)).toContain('limit=10')
    expect(String(url)).toContain('offset=20')
    expect(URL.createObjectURL).toHaveBeenCalled()
  })

  it('Exportar TXT llama al endpoint longitudinal con format=text', async () => {
    fetchMock.mockResolvedValue(
      binaryResponse({
        headers: {
          'content-type': 'text/plain; charset=utf-8',
          'content-disposition': 'attachment; filename="p001_historia_clinica_x.txt"',
        },
      }),
    )
    const user = userEvent.setup()
    render(
      <ClinicalRecordExportActions
        devUserId="u-admin"
        role="admin"
        patientId="p-1"
        limit={10}
        offset={0}
      />,
    )

    await user.click(screen.getByRole('button', { name: /exportar txt/i }))

    const [url] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('format=text')
  })

  it('un 409 por superar clinical_record_export_max_sessions se muestra tal cual, nunca como error genérico', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: 'conflict',
            message:
              'El paciente tiene más sesiones que el máximo exportable en una sola petición; ' +
              'use limit/offset para segmentar la exportación.',
          },
        },
        { status: 409 },
      ),
    )
    const user = userEvent.setup()
    render(
      <ClinicalRecordExportActions
        devUserId="u-admin"
        role="admin"
        patientId="p-1"
        limit={100}
        offset={0}
      />,
    )

    await user.click(screen.getByRole('button', { name: /exportar pdf/i }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(/conflicto/i)
    expect(alert).toHaveTextContent(/use limit\/offset para segmentar la exportación/i)
    expect(alert).not.toHaveTextContent(/error inesperado/i)
  })
})
