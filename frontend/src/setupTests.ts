import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import '@testing-library/jest-dom/vitest'

// Sin `globals: true` en la config de Vitest, la limpieza automática de
// Testing Library (basada en detectar un `afterEach` global) no se
// registra sola; se hace explícita aquí para que cada test empiece con
// un DOM limpio.
afterEach(() => {
  cleanup()
})
