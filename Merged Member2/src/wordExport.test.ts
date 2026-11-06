import { writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { Packer } from 'docx'
import { strFromU8, unzipSync } from 'fflate'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { Finding, RetrievalResult, RetrievedPassage } from './types'
import { buildFindingsReport, buildSearchReport } from './wordExport'

const passage: RetrievedPassage = {
  chunk_id: 'ich-q2-p7-c0',
  text: 'Synthetic passage text about validation characteristics.\nSecond line.',
  metadata: {
    chunk_id: 'ich-q2-p7-c0', source_title: 'Validation of Analytical Procedures', issuing_organization: 'ICH',
    source_identifier: 'ICH Q2(R2)', document_version: 'Final Version (Step 4)', publication_date: '2023-11-01',
    effective_date: null, page_number: 7, ctd_section: '3.2.S.4.3', document_type: 'guideline',
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
  const buf = await Packer.toBuffer(doc)
  // Optional: WORD_OUT=<dir> writes the files so they can be opened in Word.
  if (process.env.WORD_OUT) writeFileSync(join(process.env.WORD_OUT, name), buf)
  return strFromU8(unzipSync(new Uint8Array(buf))['word/document.xml'])
}

describe('Word export', () => {
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

  it('leaves an empty red review box when there is no comment', async () => {
    const xml = await documentXml(await buildFindingsReport([finding]), 'findings-empty.docx')
    expect(xml).toContain('Assessor comment')
    expect(xml).not.toContain('robustness')
  })

  it('builds a search report with a results table', async () => {
    const result: RetrievalResult = {
      query_fingerprint: 'x', filters: {}, knowledge_base_size: 248, candidates_considered: 10, reranked: true,
      embedding_model: 'BAAI/bge-large-en-v1.5', reranker_model: 'BAAI/bge-reranker-base', passages: [passage], latency_ms: 812,
    }
    const xml = await documentXml(
      await buildSearchReport('What is validated?', { ctd_sections: ['3.2.S.4.3'], include_parent_sections: true }, result),
      'search-sample.docx')
    expect(xml).toContain('What is validated?')
    expect(xml).toContain('0.812') // similarity score in the table
    expect((xml.match(/<w:tbl>/g) ?? []).length).toBe(2) // search details, results
  })
})
