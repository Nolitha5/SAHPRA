import { describe, expect, it } from 'vitest'
import { pageText } from './pages'

describe('pageText', () => {
  it('shows the printed page with the PDF page when they differ', () => {
    expect(pageText(7, '3')).toBe('p.3 (PDF p.7)')
    expect(pageText(7, '3', true)).toBe('3 (PDF 7)')
    expect(pageText(9, '317', true)).toBe('317 (PDF 9)')
    expect(pageText(4, 'ii')).toBe('p.ii (PDF p.4)')
  })
  it('shows one number when they match or no printed number was found', () => {
    expect(pageText(30, '30')).toBe('p.30')
    expect(pageText(1, null)).toBe('p.1')
    expect(pageText(1, undefined, true)).toBe('1')
  })
  it('handles a missing page', () => {
    expect(pageText(null, null)).toBe('')
    expect(pageText(null, null, true)).toBe('n/a')
  })
})
