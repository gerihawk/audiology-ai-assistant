import { describe, expect, it } from 'vitest'
import {
  canApprove,
  canEdit,
  canProposeAnamnesisUpdate,
  canReadArtifacts,
  canReject,
  canTriggerPipeline,
} from './permissions'

describe('permisos de aiPipeline', () => {
  it('canReadArtifacts permite a admin, audiologist y viewer; no a un rol indefinido', () => {
    expect(canReadArtifacts('admin')).toBe(true)
    expect(canReadArtifacts('audiologist')).toBe(true)
    expect(canReadArtifacts('viewer')).toBe(true)
    expect(canReadArtifacts(undefined)).toBe(false)
  })

  it('canTriggerPipeline: admin siempre, audiologist solo en sus propias sesiones, viewer nunca', () => {
    expect(canTriggerPipeline('admin', 'u-otro', 'u-admin')).toBe(true)
    expect(canTriggerPipeline('audiologist', 'u-audiologist', 'u-audiologist')).toBe(true)
    expect(canTriggerPipeline('audiologist', 'u-otro', 'u-audiologist')).toBe(false)
    expect(canTriggerPipeline('viewer', 'u-viewer', 'u-viewer')).toBe(false)
  })

  it('canApprove y canReject siguen la misma regla de propiedad que canTriggerPipeline', () => {
    expect(canApprove('admin', 'u-otro', 'u-admin')).toBe(true)
    expect(canApprove('audiologist', 'u-audiologist', 'u-audiologist')).toBe(true)
    expect(canApprove('audiologist', 'u-otro', 'u-audiologist')).toBe(false)
    expect(canApprove('viewer', 'u-viewer', 'u-viewer')).toBe(false)

    expect(canReject('admin', 'u-otro', 'u-admin')).toBe(true)
    expect(canReject('audiologist', 'u-audiologist', 'u-audiologist')).toBe(true)
    expect(canReject('audiologist', 'u-otro', 'u-audiologist')).toBe(false)
    expect(canReject('viewer', 'u-viewer', 'u-viewer')).toBe(false)
  })

  it('canEdit y canProposeAnamnesisUpdate reflejan AIArtifactAction.EDIT (misma regla de propiedad)', () => {
    expect(canEdit('admin', 'u-otro', 'u-admin')).toBe(true)
    expect(canEdit('audiologist', 'u-audiologist', 'u-audiologist')).toBe(true)
    expect(canEdit('audiologist', 'u-otro', 'u-audiologist')).toBe(false)
    expect(canEdit('viewer', 'u-viewer', 'u-viewer')).toBe(false)

    expect(canProposeAnamnesisUpdate('admin', 'u-otro', 'u-admin')).toBe(true)
    expect(canProposeAnamnesisUpdate('audiologist', 'u-audiologist', 'u-audiologist')).toBe(true)
    expect(canProposeAnamnesisUpdate('audiologist', 'u-otro', 'u-audiologist')).toBe(false)
    expect(canProposeAnamnesisUpdate('viewer', 'u-viewer', 'u-viewer')).toBe(false)
  })
})
