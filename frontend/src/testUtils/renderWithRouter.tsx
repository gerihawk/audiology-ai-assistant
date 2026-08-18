import { render } from '@testing-library/react'
import type { RenderOptions } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

interface RenderWithRouterOptions extends Omit<RenderOptions, 'wrapper'> {
  /** Ruta inicial del historial simulado. */
  route?: string
  /** Patrón de ruta bajo el que se monta `ui` (por defecto, catch-all). */
  path?: string
}

/** Envuelve `ui` en un `MemoryRouter` para componentes que usan `Link`,
 * `useNavigate` o `useParams` — evita repetir el wrapper en cada test. */
export function renderWithRouter(
  ui: ReactElement,
  { route = '/', path = '*', ...options }: RenderWithRouterOptions = {},
) {
  const wrap = (element: ReactElement) => (
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path={path} element={element} />
      </Routes>
    </MemoryRouter>
  )
  const result = render(wrap(ui), options)
  return {
    ...result,
    // El `rerender` de Testing Library sustituye todo el árbol montado —
    // hay que reenvolverlo en el mismo `MemoryRouter`/`Routes`, si no el
    // siguiente render pierde el contexto de router.
    rerender: (nextUi: ReactElement) => result.rerender(wrap(nextUi)),
  }
}
