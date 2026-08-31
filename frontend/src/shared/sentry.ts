import * as Sentry from '@sentry/react'

/**
 * Sentry — EXCLUSIVAMENTE error tracking (Fase 10.6). Sin performance
 * tracing (`tracesSampleRate: 0`), sin Session Replay (`@sentry/replay`
 * llega como dependencia transitiva de `@sentry/browser` pero nunca se
 * importa ni se activa aquí) ni Profiling. Saneamiento agresivo en
 * `beforeSend`/`beforeBreadcrumb` — ver docs/privacy-and-security.md
 * §2/§3/§6 y docs/data-model.md §2 para qué campos del dominio son
 * PHI/PII real (identidad de pacientes, contenido de
 * transcripción/anamnesis, notas administrativas de texto libre) frente a
 * lo que no lo es (UUIDs, roles, códigos de estado).
 */

const HEADER_ALLOWLIST = new Set(['content-type', 'x-request-id'])

function sanitizeRequest(request: Sentry.RequestEventData | undefined): void {
  if (!request) return
  delete request.data
  delete request.cookies
  if (request.headers) {
    request.headers = Object.fromEntries(
      Object.entries(request.headers).filter(([key]) => HEADER_ALLOWLIST.has(key.toLowerCase())),
    )
  }
}

export function beforeSend(event: Sentry.ErrorEvent): Sentry.ErrorEvent | null {
  sanitizeRequest(event.request)
  // `extra` es un cajón de sastre libre (`Sentry.captureException(err, {
  // extra: {...} })`); nada del código actual lo usa, pero si algún día se
  // añade, no debe poder colar datos de formulario/estado de componente
  // sin pasar antes por este saneamiento.
  delete event.extra
  return event
}

export function beforeBreadcrumb(breadcrumb: Sentry.Breadcrumb): Sentry.Breadcrumb | null {
  // Defensa en profundidad: los breadcrumbs `fetch`/`xhr` de
  // `breadcrumbsIntegration` ya excluyen el cuerpo de la petición/respuesta
  // por diseño de la SDK (solo `method`/`url`/`status_code`); el vector
  // real de fuga es `console` (captura los argumentos completos pasados a
  // `console.*`), desactivado explícitamente más abajo — este filtro cubre
  // el caso de que algo lo reactive sin querer en el futuro.
  if (breadcrumb.category === 'console') return null
  return breadcrumb
}

export function initSentry(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN
  if (!dsn) return
  Sentry.init({
    dsn,
    environment: import.meta.env.MODE,
    // `VITE_SENTRY_RELEASE` viene de `RAILWAY_GIT_COMMIT_SHA`, una
    // variable de Railway (no nuestra) inyectada en build-time del
    // Dockerfile (ver frontend/Dockerfile.prod) — solo poblada en deploys
    // disparados desde GitHub; `undefined` en local/dev, que Sentry trata
    // como "sin release". Si tras un deploy real el campo `release`
    // aparece vacío en Sentry, es señal de que aquí no llega — revisarlo
    // entonces, no asumir que funciona solo porque el build compila.
    release: import.meta.env.VITE_SENTRY_RELEASE,
    sendDefaultPii: false,
    tracesSampleRate: 0,
    integrations: [Sentry.breadcrumbsIntegration({ console: false })],
    beforeSend,
    beforeBreadcrumb,
  })
}
