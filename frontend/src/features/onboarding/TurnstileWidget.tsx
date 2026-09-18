import { useEffect, useId, useRef } from 'react'

/** Widget de Cloudflare Turnstile en `POST /clinics/signup` (Fase 12,
 * hito 12.4 ampliado, decisión del 2026-09-18 — ver
 * app/onboarding/service.py::signup_clinic y docs/fase-12-rfc.md §6).
 *
 * Sin `VITE_TURNSTILE_SITE_KEY` configurada (desarrollo local, o
 * cualquier entorno donde Gerard no haya creado todavía un site key real
 * en el dashboard de Cloudflare): no renderiza nada y entrega un token
 * vacío de inmediato — coherente con `TURNSTILE_PROVIDER=mock` (default
 * del backend en app/core/config.py), que acepta cualquier valor. Con
 * site key configurada, carga el script oficial de Cloudflare una sola
 * vez (compartido si hay varios widgets en la página) y renderiza el
 * challenge — normalmente invisible, sin puzzles visuales.
 */

declare global {
  interface Window {
    turnstile?: {
      render: (
        container: HTMLElement,
        options: {
          sitekey: string
          callback: (token: string) => void
          'expired-callback'?: () => void
          'error-callback'?: () => void
        },
      ) => string
      remove: (widgetId: string) => void
    }
    __turnstileScriptPromise__?: Promise<void>
  }
}

const TURNSTILE_SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js'

function loadTurnstileScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve()
  if (!window.__turnstileScriptPromise__) {
    window.__turnstileScriptPromise__ = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = TURNSTILE_SCRIPT_SRC
      script.async = true
      script.defer = true
      script.onload = () => resolve()
      script.onerror = () =>
        reject(new Error('No se pudo cargar el script de Cloudflare Turnstile.'))
      document.head.appendChild(script)
    })
  }
  return window.__turnstileScriptPromise__
}

interface TurnstileWidgetProps {
  onToken: (token: string) => void
}

export function TurnstileWidget({ onToken }: TurnstileWidgetProps) {
  const containerId = useId()
  const containerRef = useRef<HTMLDivElement>(null)
  const widgetIdRef = useRef<string | null>(null)
  const siteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY

  useEffect(() => {
    if (!siteKey) {
      // Sin site key: no hay widget que renderizar — ver docstring.
      onToken('')
      return
    }

    let cancelled = false
    void loadTurnstileScript().then(() => {
      if (cancelled || !containerRef.current || !window.turnstile) return
      widgetIdRef.current = window.turnstile.render(containerRef.current, {
        sitekey: siteKey,
        callback: (token) => onToken(token),
        'expired-callback': () => onToken(''),
        'error-callback': () => onToken(''),
      })
    })

    return () => {
      cancelled = true
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onToken es estable en el único llamador (SignupPage)
  }, [siteKey])

  if (!siteKey) return null

  return <div id={containerId} ref={containerRef} />
}
