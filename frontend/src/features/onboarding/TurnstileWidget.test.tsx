import { render, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TurnstileWidget } from './TurnstileWidget'

describe('TurnstileWidget', () => {
  const originalSiteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY

  afterEach(() => {
    // `import.meta.env` es de solo lectura por tipo, pero vitest permite
    // reasignarlo en runtime — se restaura para no filtrar entre tests.
    ;(import.meta.env as { VITE_TURNSTILE_SITE_KEY?: string }).VITE_TURNSTILE_SITE_KEY =
      originalSiteKey
    delete window.turnstile
    delete window.__turnstileScriptPromise__
  })

  it('sin VITE_TURNSTILE_SITE_KEY: no renderiza nada y entrega un token vacío de inmediato', async () => {
    // OJO: asignar `undefined` aquí NO simula "sin configurar" — `import.meta.env`
    // se comporta como `process.env` (todo valor asignado se coacciona a string,
    // `undefined` se convierte literalmente en la cadena "undefined", que es
    // truthy). `''` es la representación real de "sin configurar" (mismo valor
    // que deja `VITE_TURNSTILE_SITE_KEY=` vacío en .env.example).
    ;(import.meta.env as { VITE_TURNSTILE_SITE_KEY?: string }).VITE_TURNSTILE_SITE_KEY = ''
    const onToken = vi.fn()

    const { container } = render(<TurnstileWidget onToken={onToken} />)

    await waitFor(() => expect(onToken).toHaveBeenCalledWith(''))
    expect(container).toBeEmptyDOMElement()
  })

  it('con site key configurada: renderiza el widget con el sitekey correcto y reenvía el token del callback', async () => {
    ;(import.meta.env as { VITE_TURNSTILE_SITE_KEY?: string }).VITE_TURNSTILE_SITE_KEY =
      'site-key-de-test'
    const onToken = vi.fn()
    const renderWidget = vi.fn().mockReturnValue('widget-id-1')
    // `window.turnstile` ya presente antes del render: `loadTurnstileScript`
    // ve `window.turnstile` definido y no llega a insertar ningún <script>
    // real (jsdom no ejecutaría su contenido de todos modos) — mismo
    // resultado que si el script de Cloudflare ya hubiera cargado.
    window.turnstile = { render: renderWidget, remove: vi.fn() }

    render(<TurnstileWidget onToken={onToken} />)

    await waitFor(() => expect(renderWidget).toHaveBeenCalled())
    const [, options] = renderWidget.mock.calls[0] as [
      HTMLElement,
      { sitekey: string; callback: (t: string) => void },
    ]
    expect(options.sitekey).toBe('site-key-de-test')

    options.callback('token-del-widget')
    expect(onToken).toHaveBeenCalledWith('token-del-widget')
  })
})
