import { describe, expect, it } from 'vitest'
import { buildRequest, routeAgent } from './searchRouting'

const filters = { include_parent_sections: true, applicability_statuses: [] }

describe('search routing', () => {
  it('sends 3.2.S.4 questions to S.4 Control and everything else to Evidence/RERA', () => {
    expect(routeAgent('auto', '3.2.S.4')).toBe('s4-control')
    expect(routeAgent('auto', '3.2.S.4.3')).toBe('s4-control')
    expect(routeAgent('auto', '3.2.S.7')).toBe('evidence-rera')
    expect(routeAgent('auto', '3.2.S.40')).toBe('evidence-rera') // not a 3.2.S.4 subsection
    expect(routeAgent('auto', '')).toBe('evidence-rera')
    expect(routeAgent('s4-control', '3.2.S.7')).toBe('s4-control') // a manual choice wins
  })

  it('"Any section" searches everything without a section filter', () => {
    const req = buildRequest('evidence-rera', 'q', '', filters, true)
    expect(req.filters?.ctd_sections).toEqual([])
    expect(req.parameters).toMatchObject({ use_section_filter: false, use_reranker: true })
  })

  it('a chosen section filters Evidence/RERA', () => {
    const req = buildRequest('evidence-rera', 'q', '3.2.S.7', filters, false)
    expect(req.ctd_section).toBe('3.2.S.7')
    expect(req.filters?.ctd_sections).toEqual(['3.2.S.7'])
    expect(req.parameters).toMatchObject({ use_section_filter: true, use_reranker: false })
  })

  it('S.4 Control gets its topic from the section, falling back to 3.2.S.4', () => {
    expect(buildRequest('s4-control', 'q', '3.2.S.4.1', filters, true).ctd_section).toBe('3.2.S.4.1')
    expect(buildRequest('s4-control', 'q', '3.2.S.7', filters, true).ctd_section).toBe('3.2.S.4')
    expect(buildRequest('s4-control', 'q', '', filters, true).filters?.ctd_sections).toEqual([])
  })
})
