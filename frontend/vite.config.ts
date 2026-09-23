import { defineConfig, type Plugin } from 'vitest/config'
import react from '@vitejs/plugin-react'

// `@types/node` no está instalado (no hace falta añadirlo por esta única
// lectura) — declaración ambiental mínima para poder leer `process.env`
// dentro de este fichero de configuración (corre en Node, no en el
// navegador; `import.meta.env` de Vite no existe aquí). Verificado en
// vivo: sin esto, `npm run build` (tsc -b) falla con TS2580 "Cannot find
// name 'process'" — rompía el build de producción real.
declare const process: { env: Record<string, string | undefined> }

// Content-Security-Policy del servidor de desarrollo (cierre del hallazgo
// medio del red team, docs/security/red-team-app-2026-09-22.md §C2) — más
// permisiva que la de producción (nginx.conf.template) exclusivamente por
// lo que exige el propio HMR de Vite en dev, nunca código de la app:
//   - connect-src ws://.../localhost:5173: WebSocket del cliente HMR de
//     Vite (recarga en caliente), no algo que use la app.
//   - Mismo origen de API que en producción por defecto
//     (VITE_API_BASE_URL, "http://localhost:8000" si no se sobreescribe —
//     ver docker-compose.yml).
// El resto (script-src/style-src/frame-src de Turnstile, style-src
// 'unsafe-inline' del único style={{}} de ConfidenceIndicator.tsx) es
// idéntico a producción.
const API_ORIGIN = process.env.VITE_API_BASE_URL || 'http://localhost:8000'
// Verificado en vivo (consola real del navegador, no supuesto): el
// preamble inline que @vitejs/plugin-react inyecta en dev para React Fast
// Refresh viola script-src sin esto — Chrome reportó el hash exacto en el
// propio mensaje de violación. Solo dev: el build de producción no tiene
// preamble inline (el runtime de React va en el bundle normal). Si al
// actualizar @vitejs/plugin-react el preamble cambia, este hash dejará de
// coincidir y habrá que reemplazarlo por el que reporte la nueva
// violación — no es un secreto ni algo que se pueda adivinar.
const DEV_REACT_PREAMBLE_HASH = "'sha256-Z2/iFzh9VMlVkEOar1f/oSHWwQk3ve1qk/C2WdsC4Xk='"
const DEV_CSP = [
  "default-src 'self'",
  `script-src 'self' https://challenges.cloudflare.com ${DEV_REACT_PREAMBLE_HASH}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  `connect-src 'self' ws://localhost:5173 ${API_ORIGIN} https://*.sentry.io`,
  'frame-src https://challenges.cloudflare.com',
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join('; ')

// `server.headers` de Vite (más abajo) NO cubre la ruta raíz `/` en Vite
// 6.4.3: verificado en el código fuente real de Vite dentro del
// contenedor — `indexHtmlMiddleware` solo aplica `server.headers` cuando
// la URL termina literalmente en `.html`, y `/` nunca la tiene (confirmado
// también en vivo con curl: la cabecera faltaba en la home pese a estar
// configurada). Este middleware de plugin cubre todas las respuestas, sin
// depender de esa condición interna.
function cspHeaderPlugin(csp: string): Plugin {
  return {
    name: 'csp-header',
    configureServer(server) {
      server.middlewares.use((_req, res, next) => {
        res.setHeader('Content-Security-Policy', csp)
        next()
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), cspHeaderPlugin(DEV_CSP)],
  server: {
    host: true,
    port: 5173,
    headers: {
      'Content-Security-Policy': DEV_CSP,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    css: false,
  },
})
