import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'
import '@testing-library/jest-dom/vitest'

// Sin `globals: true` en la config de Vitest, la limpieza automática de
// Testing Library (basada en detectar un `afterEach` global) no se
// registra sola; se hace explícita aquí para que cada test empiece con
// un DOM limpio.
afterEach(() => {
  cleanup()
})

// jsdom no implementa `ResizeObserver` — lo necesita
// `recharts`/`ResponsiveContainer` (Fase 15, panel de analítica) para medir
// su contenedor. Un stub mínimo basta: los tests no dependen de que
// realmente dispare el callback en un resize, solo de que la clase exista
// para que Recharts no lance al montarse.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

vi.stubGlobal('ResizeObserver', ResizeObserverStub)
