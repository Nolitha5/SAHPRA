import { describe, expect, it } from 'vitest'
import type { PassageMetadata } from '../types'
import { passageText, plural, sourceLabel, versionLabel } from './shared'

const meta = (overrides: Partial<PassageMetadata> = {}) => ({
  issuing_organization: 'ICH',
  source_title: 'Validation of Analytical Procedures',
  document_version: 'Final Version (Step 4)',
  page_number: 7,
  ...overrides,
}) as PassageMetadata

describe('versionLabel', () => {
  it('prefixes numeric versions only', () => {
    expect(versionLabel('1.0')).toBe('v1.0')
    expect(versionLabel('Step 4')).toBe('Step 4')
    expect(versionLabel('Final Version (Step 4)')).toBe('Final Version (Step 4)')
  })
})

describe('sourceLabel', () => {
  it('joins organisation, title, version and page', () => {
    expect(sourceLabel(meta())).toBe('ICH · Validation of Analytical Procedures · Final Version (Step 4) · p.7')
  })
  it('shows the printed page number with the PDF page', () => {
    expect(sourceLabel(meta({ page_label: '3' }))).toBe('ICH · Validation of Analytical Procedures · Final Version (Step 4) · p.3 (PDF p.7)')
  })
  it('leaves out missing version and page', () => {
    expect(sourceLabel(meta({ document_version: null, page_number: null }))).toBe('ICH · Validation of Analytical Procedures')
  })
})

describe('plural', () => {
  it('uses singular for exactly one', () => {
    expect(plural(1, 'page')).toBe('1 page')
    expect(plural(0, 'page')).toBe('0 pages')
    expect(plural(3, 'chunk')).toBe('3 chunks')
  })
})

describe('passageText', () => {
  it('marks passages that start mid-sentence', () => {
    expect(passageText('and / or controlled, and purity')).toBe('…and / or controlled, and purity')
    expect(passageText('3.1 Specifications')).toBe('3.1 Specifications')
    expect(passageText('SPECIFICATIONS: TEST')).toBe('SPECIFICATIONS: TEST')
  })
})
