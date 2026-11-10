import type { Finding, PageTable } from './types'

/** The tables on a finding's cited pages, each once, in the order the passages were cited. */
export function findingTables(f: Finding): PageTable[] {
  const seen = new Set<string>()
  const out: PageTable[] = []
  for (const p of f.regulatory_evidence) {
    for (const t of f.page_tables?.[p.chunk_id] ?? []) {
      if (!seen.has(t.table_id)) {
        seen.add(t.table_id)
        out.push(t)
      }
    }
  }
  return out
}

export const TABLE_NOTE =
  'Table read automatically from the PDF. Check the original image for exact values, footnote markers and merged cells.'
