import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { AIArtifactVersion } from '../../shared/api/types'
import { ArtifactVersionList } from './ArtifactVersionList'

function makeVersion(overrides: Partial<AIArtifactVersion> = {}): AIArtifactVersion {
  return {
    id: 'version-1',
    version_number: 1,
    content: {},
    confidence: 80,
    source: 'ai_generated',
    provider_name: 'mock-provider',
    model_name: 'mock-model',
    is_current: false,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('ArtifactVersionList', () => {
  it('muestra un mensaje explicativo cuando solo existe una versión', () => {
    render(
      <ArtifactVersionList
        versions={[makeVersion({ is_current: true })]}
        selectedVersionId="version-1"
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText(/todavía no hay más de una versión/i)).toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('lista varias versiones marcando cuál es la vigente y cuál está seleccionada', () => {
    const versions = [
      makeVersion({ id: 'v2', version_number: 2, is_current: true }),
      makeVersion({ id: 'v1', version_number: 1, is_current: false }),
    ]
    render(<ArtifactVersionList versions={versions} selectedVersionId="v2" onSelect={vi.fn()} />)

    const currentButton = screen.getByRole('button', { name: /versión 2.*vigente/i })
    expect(currentButton).toHaveAttribute('aria-current', 'true')

    const oldButton = screen.getByRole('button', { name: /versión 1/i })
    expect(oldButton).not.toHaveAttribute('aria-current', 'true')
    expect(oldButton).not.toHaveTextContent('vigente')
  })

  it('permite cambiar de versión seleccionada', async () => {
    const versions = [
      makeVersion({ id: 'v2', version_number: 2, is_current: true }),
      makeVersion({ id: 'v1', version_number: 1, is_current: false }),
    ]
    const onSelect = vi.fn()
    const user = userEvent.setup()

    render(<ArtifactVersionList versions={versions} selectedVersionId="v2" onSelect={onSelect} />)

    await user.click(screen.getByRole('button', { name: /versión 1/i }))
    expect(onSelect).toHaveBeenCalledWith(versions[1])
  })
})
