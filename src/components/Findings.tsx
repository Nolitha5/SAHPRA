import type { Citation, ComparisonRow, Finding } from '../types'
import { pageText } from '../pages'
import AssessorReview from './AssessorReview'
import { PassageCard, QaPill, StatusPill, plural, versionLabel } from './shared'

// One agent finding, shown as Word-style tables, with the red assessor-review box.
// Used by the Search tab, which sends every question to an agent.

const FLAG_TEXT: Record<string, string> = {
  knowledge_base_empty: 'Knowledge base is empty',
  no_passages_matched_filters: 'No passages matched',
  retrieved_passages_below_relevance_threshold: 'Retrieved passages below relevance threshold',
  contains_superseded_or_withdrawn_source: 'Superseded or withdrawn source',
  contains_draft_source: 'Draft source',
  applicability_status_unknown_for_some_sources: 'Applicability unknown for some sources',
  incomplete_provenance_for_some_sources: 'Incomplete provenance',
  synthetic_test_data_not_real_evidence: 'Synthetic test data, not real evidence',
  instruction_like_text_in_retrieved_passage: 'Instruction-like text in a passage',
  multiple_versions_of_same_document: 'Multiple versions of one document',
}

const OUTCOME: Record<ComparisonRow['outcome'], { label: string; cls: string }> = {
  within_criteria: { label: 'Within', cls: 'pill-green' },
  outside_criteria: { label: 'Outside', cls: 'pill-red' },
  at_least_as_strict: { label: 'At least as strict', cls: 'pill-green' },
  less_strict: { label: 'Less strict', cls: 'pill-red' },
  not_compared: { label: 'Not compared', cls: 'pill-yellow' },
}

function citationDetails(c: Citation): string {
  return [c.document_version ? versionLabel(c.document_version) : null, c.publication_date].filter(Boolean).join(' · ') || 'n/a'
}

const score = (v: number | null | undefined) => (v == null ? 'n/a' : v.toFixed(3))

export function FindingCard({ f }: { f: Finding }) {
  const rows = f.metadata.confidential_comparison_rows ?? []
  const flags = f.metadata.flags ?? []
  const weaker = f.metadata.below_threshold_candidates ?? []
  const agentLabel = f.agent_name === 'evidence_rera' ? 'Evidence/RERA' : 'S.4 Control'
  // Search scores for each cited passage (citations and evidence share chunk_id).
  const scores = new Map(f.regulatory_evidence.map(p => [p.chunk_id, p]))
  const retrieval = f.metadata.retrieval
  return (
    <article className="card section-gap finding">
      <header className="finding-head">
        <div>
          <div className="finding-kicker">{agentLabel} · CTD {f.ctd_section}</div>
          <h3 className="finding-question">{f.assessment_question}</h3>
        </div>
      </header>

      <div className="card-body stack">
        <div className="doc-section">
          <h4 className="doc-heading">Finding details</h4>
          <div className="table-wrap">
            <table className="doc-table doc-table-details">
              <tbody>
                <tr><th scope="row">Agent</th><td>{agentLabel}</td></tr>
                <tr><th scope="row">CTD section</th><td>{f.ctd_section}</td></tr>
                <tr><th scope="row">QA status</th><td><QaPill status={f.qa_status} /></td></tr>
                <tr><th scope="row">Evidence status</th><td>{f.evidence_status.replace(/_/g, ' ')}</td></tr>
                <tr className="doc-row-emphasis"><th scope="row">Conclusion</th><td>{f.conclusion}</td></tr>
                <tr><th scope="row">Rationale</th><td>{f.rationale}</td></tr>
                <tr><th scope="row">Uncertainty</th><td>{f.uncertainty}</td></tr>
                <tr>
                  <th scope="row">Flags</th>
                  <td>{flags.length
                    ? <div className="row-actions" style={{ flexWrap: 'wrap' }}>{flags.map(fl => <span key={fl} className="pill pill-yellow">{FLAG_TEXT[fl] ?? fl}</span>)}</div>
                    : 'None'}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        {rows.length > 0 && (
          <div className="doc-section">
            <h4 className="doc-heading">Comparison</h4>
            <div className="table-wrap">
              <table className="doc-table table-stack">
                <thead><tr><th>Test</th><th>Batch</th><th>Reported</th><th>Criterion</th><th>Outcome</th><th>Reason</th></tr></thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      <td data-label="Test">{r.test_name}</td>
                      <td className="text-mono" data-label="Batch">{r.batch_id ?? 'n/a'}</td>
                      <td className="text-mono" data-label="Reported">{r.reported_value} {r.reported_unit}</td>
                      <td className="text-mono" data-label="Criterion">{r.criterion_text ?? 'n/a'}</td>
                      <td data-label="Outcome"><span className={`pill ${OUTCOME[r.outcome].cls}`}>{OUTCOME[r.outcome].label}</span>{r.borderline && <> <span className="pill pill-yellow">borderline</span></>}</td>
                      <td data-label="Reason">{r.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="doc-section">
          <h4 className="doc-heading">Citations ({f.citations.length})</h4>
          {f.citations.length > 0 ? (
            <div className="table-wrap">
              <table className="doc-table table-stack">
                <thead><tr><th className="num">#</th><th>Source</th><th>Document</th><th>Version · date</th><th className="num">Page</th><th>CTD</th><th>Status</th><th className="num">Similarity</th><th className="num">Rerank</th></tr></thead>
                <tbody>
                  {f.citations.map((c, i) => (
                    <tr key={c.chunk_id}>
                      <td className="num" data-label="#">{i + 1}</td>
                      <td data-label="Source"><b>{c.issuing_organization}</b> · {c.source_title}</td>
                      <td data-label="Document">{c.source_identifier}</td>
                      <td data-label="Version">{citationDetails(c)}</td>
                      <td className="num" data-label="Page">{pageText(c.page_number, c.page_label, true)}</td>
                      <td data-label="CTD">{c.ctd_section ?? 'n/a'}</td>
                      <td data-label="Status">
                        <StatusPill status={c.applicability_status} />
                        {!c.provenance_complete && <> <span className="pill pill-yellow" title={c.missing_provenance.join(', ')}>incomplete</span></>}
                      </td>
                      <td className="num" data-label="Similarity">{score(scores.get(c.chunk_id)?.retrieval_score)}</td>
                      <td className="num" data-label="Rerank">{score(scores.get(c.chunk_id)?.rerank_score)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="text-muted">No citations: no passage met the evidence threshold.</p>}
          {retrieval && (
            <p className="text-muted" style={{ fontSize: 12 }}>
              Searched {retrieval.knowledge_base_size} passages · {retrieval.candidates_considered} candidates ·{' '}
              {retrieval.reranked ? 'reranked' : 'not reranked'} · {Math.round(retrieval.latency_ms)} ms
            </p>
          )}
        </div>

        {f.regulatory_evidence.length > 0 && (
          <details>
            <summary>Show the {plural(f.regulatory_evidence.length, 'supporting passage')}</summary>
            <div className="stack" style={{ marginTop: 12 }}>
              {f.regulatory_evidence.map(p => <PassageCard key={p.chunk_id} p={p} />)}
            </div>
          </details>
        )}

        {weaker.length > 0 && (
          <details>
            <summary>{plural(weaker.length, 'weaker candidate')} not used as evidence</summary>
            <ul className="citations" style={{ marginTop: 8 }}>
              {weaker.map(c => <li key={c.chunk_id}>{c.source}</li>)}
            </ul>
          </details>
        )}

        <AssessorReview findingId={f.finding_id} />

        <p className="finding-footer">Finding {f.finding_id} · generated {new Date(f.created_at).toLocaleString()}</p>
      </div>
    </article>
  )
}
