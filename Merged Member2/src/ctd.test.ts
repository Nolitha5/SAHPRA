import { describe, expect, it } from 'vitest'
import { CTD_SECTIONS, ctdAncestors, ctdTitle, withinSection } from './ctd'

describe('CTD headings', () => {
  it('lists every heading once, including the tags used in the knowledge base', () => {
    expect(new Set(CTD_SECTIONS).size).toBe(CTD_SECTIONS.length)
    for (const tag of ['3.2', '3.2.S', '3.2.S.2', '3.2.S.3', '3.2.S.4', '3.2.S.4.1', '3.2.S.4.2', '3.2.S.4.3', '3.2.S.7', '3.2.P.2']) {
      expect(CTD_SECTIONS).toContain(tag)
    }
    // all 3.2.S headings of ICH M4Q(R1): 7 sections + 19 subsections, plus 3.2.S itself
    expect(CTD_SECTIONS.filter(c => c.startsWith('3.2.S')).length).toBe(27)
  })

  it('names headings from ICH M4Q', () => {
    expect(ctdTitle('3.2.S.2.3')).toBe('Control of materials')
    expect(ctdTitle('3.2.S.7.2')).toBe('Post-approval stability protocol and stability commitment')
  })

  it('parent headings match the backend rule', () => {
    expect(ctdAncestors('3.2.S.4.1')).toEqual(['3.2.S.4', '3.2.S', '3.2'])
    expect(ctdAncestors('3.2.S')).toEqual(['3.2'])
    expect(ctdAncestors('3.2.P.2')).toEqual(['3.2.P', '3.2'])
  })

  it('a section contains its subsections but not look-alikes', () => {
    expect(withinSection('3.2.S.4.1', '3.2.S.4')).toBe(true)
    expect(withinSection('3.2.S.4', '3.2.S.4')).toBe(true)
    expect(withinSection('3.2.S.40', '3.2.S.4')).toBe(false)
  })
})
