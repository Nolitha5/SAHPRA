import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { Packer } from 'docx'
import { strFromU8, unzipSync } from 'fflate'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { Finding, RetrievedPassage } from './types'
import { buildFindingsReport } from './wordExport'

const passage: RetrievedPassage = {
  chunk_id: 'ich-q2-p7-c0',
  text: 'Synthetic passage text about validation characteristics.\nSecond line.',
  metadata: {
    chunk_id: 'ich-q2-p7-c0', source_title: 'Validation of Analytical Procedures', issuing_organization: 'ICH',
    source_identifier: 'ICH Q2(R2)', document_version: 'Final Version (Step 4)', publication_date: '2023-11-01',
    effective_date: null, page_number: 7, page_label: '3', ctd_section: '3.2.S.4.3', document_type: 'guideline',
    applicability_status: 'current', content_hash: 'abc', provenance_complete: true,
  } as unknown as RetrievedPassage['metadata'],
  retrieval_method: 'vector_search', retrieval_score: 0.81234, retrieval_rank: 1, rerank_score: 2.5, rerank_rank: 1,
  untrusted_content_flags: [],
}

const finding = {
  schema_version: '1', finding_id: 'F-test-1', agent_name: 'evidence_rera', ctd_section: '3.2.S.4.3',
  assessment_question: 'Which characteristics are validated for an assay?', sponsor_evidence: [],
  regulatory_evidence: [passage],
  citations: [{ ...passage.metadata, missing_provenance: [] }],
  conclusion: 'Candidate regulatory evidence retrieved.', rationale: 'Searched 248 passages.', uncertainty: 'Scores are not probabilities.',
  qa_status: 'partial', evidence_status: 'candidate_evidence_found', requires_human_review: true,
  metadata: { flags: ['contains_draft_source'] }, created_at: '2026-11-06T10:00:00Z',
} as unknown as Finding

async function documentXml(doc: Awaited<ReturnType<typeof buildFindingsReport>>, name: string): Promise<string> {
  return (await documentFiles(doc, name))['word/document.xml']
}

async function documentFiles(doc: Awaited<ReturnType<typeof buildFindingsReport>>, name: string) {
  const buf = await Packer.toBuffer(doc)
  // Optional: WORD_OUT=<dir> writes the files so they can be opened in Word.
  if (process.env.WORD_OUT) writeFileSync(join(process.env.WORD_OUT, name), buf)
  const files = unzipSync(new Uint8Array(buf))
  return Object.fromEntries(Object.entries(files).map(([k, v]) => [k, k.endsWith('.xml') ? strFromU8(v) : `${v.length} bytes`]))
}

// A 1x1 PNG, standing in for an original table image.
const PNG = Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='), c => c.charCodeAt(0))
const table = {
  table_id: 'ich-q3a-r2-step-4-p12-t1', source_identifier: 'ICH Q3A(R2)', page_number: 12, page_label: '8', index_on_page: 1,
  rows: [['Maximum Daily Dose', 'Reporting Threshold'], ['≤ 2g/day', '0.05%'], ['> 2g/day', '0.03%']],
  width: 948, height: 225, image_url: '/api/tables/ich-q3a-r2-step-4-p12-t1/image',
}

describe('Word export', () => {
  it('adds the tables of the cited pages as Word tables with the original image', async () => {
    const withTable = { ...finding, page_tables: { [passage.chunk_id]: [table] } } as Finding
    const files = await documentFiles(await buildFindingsReport([withTable], { [table.table_id]: PNG }), 'findings-table.docx')
    const xml = files['word/document.xml']
    expect(xml).toContain('Tables on the cited pages (1)')
    expect(xml).toContain('ICH Q3A(R2) · p.8 (PDF p.12) · table 1')
    expect(xml).toContain('0.05%')
    expect(Object.keys(files).some(f => f.startsWith('word/media/'))).toBe(true) // the image is embedded
  })

  it('notes a missing table image instead of failing', async () => {
    const withTable = { ...finding, page_tables: { [passage.chunk_id]: [table] } } as Finding
    const xml = await documentXml(await buildFindingsReport([withTable]), 'findings-noimage.docx')
    expect(xml).toContain('Original table image not available')
  })

  const store = new Map<string, string>()
  beforeEach(() => {
    store.clear()
    globalThis.localStorage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    } as Storage
  })
  afterEach(() => { delete (globalThis as { localStorage?: Storage }).localStorage })

  it('builds a findings report with tables and the assessor comment in red', async () => {
    store.set('m2-assessor-comment:F-test-1', JSON.stringify({ text: 'Evidence adequate; ask for robustness data.', savedAt: '2026-11-06T11:00:00Z' }))
    const xml = await documentXml(await buildFindingsReport([finding]), 'findings-sample.docx')
    expect(xml).toContain('Which characteristics are validated for an assay?')
    expect(xml).toContain('Evidence adequate; ask for robustness data.')
    expect(xml).toMatch(/<w:color w:val="C81E1E"\/>[\s\S]*Evidence adequate/)
    expect((xml.match(/<w:tbl>/g) ?? []).length).toBe(3) // details, citations, assessor review
    expect(xml).not.toMatch(/\n<\/w:t>/) // no raw newlines inside text runs
  })

  it('puts the assessor review last, after the supporting passages', async () => {
    const withTable = { ...finding, page_tables: { [passage.chunk_id]: [table] } } as Finding
    const xml = await documentXml(await buildFindingsReport([withTable], { [table.table_id]: PNG }), 'findings-order.docx')
    const order = ['Citations', 'Tables on the cited pages', 'Supporting passages', 'Assessor review'].map(h => xml.indexOf(h))
    expect(order.every(i => i >= 0)).toBe(true)
    expect([...order].sort((a, b) => a - b)).toEqual(order)
    expect(xml.lastIndexOf('Assessor comment')).toBeGreaterThan(xml.lastIndexOf('Synthetic passage text'))
  })

  it('leaves an empty red review box when there is no comment', async () => {
    const xml = await documentXml(await buildFindingsReport([finding]), 'findings-empty.docx')
    expect(xml).toContain('Assessor comment')
    expect(xml).not.toContain('robustness')
  })

  it('shows the search scores of each cited passage', async () => {
    const xml = await documentXml(await buildFindingsReport([finding]), 'findings-scores.docx')
    expect(xml).toContain('Similarity')
    expect(xml).toContain('0.812') // retrieval score of the cited passage
    expect(xml).toContain('2.500') // rerank score
    expect(xml).toContain('3 (PDF 7)') // printed page with the PDF page
  })
})
