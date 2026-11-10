import { describe, expect, it } from 'vitest'
import { findingTables } from './findingTables'
import type { Finding } from './types'

const t = (id: string) => ({ table_id: id, source_identifier: 'X', page_number: 1, page_label: null, index_on_page: 1,
  rows: [['a', 'b'], ['1', '2']], width: 10, height: 10, image_url: `/api/tables/${id}/image` })

describe('findingTables', () => {
  it('lists each table once, in the order the passages were cited', () => {
    const f = {
      regulatory_evidence: [{ chunk_id: 'c2' }, { chunk_id: 'c1' }, { chunk_id: 'c3' }],
      page_tables: { c1: [t('t-a')], c2: [t('t-b'), t('t-a')], c3: [] },
    } as unknown as Finding
    expect(findingTables(f).map(x => x.table_id)).toEqual(['t-b', 't-a'])
  })
  it('handles findings without tables', () => {
    expect(findingTables({ regulatory_evidence: [] } as unknown as Finding)).toEqual([])
  })
})
