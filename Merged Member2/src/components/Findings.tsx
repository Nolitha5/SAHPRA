import type { FormEvent } from 'react'
import { useState } from 'react'
import { api, CTD_SECTIONS } from '../api'
import type { AgentRequest, Citation, ComparisonRow, Finding } from '../types'
import { downloadFindingsReport } from '../wordExport'
import AssessorReview from './AssessorReview'
import WordToolbar from './WordToolbar'
import { PassageCard, QaPill, StatusPill, plural, versionLabel } from './shared'

type Agent = 'evidence-rera' | 's4-control'

const S4_TOPICS: { value: string; label: string; section: string }[] = [
  { value: 'general', label: 'General (3.2.S.4)', section: '3.2.S.4' },
  { value: 'specification', label: 'Specification (3.2.S.4.1)', section: '3.2.S.4.1' },
  { value: 'analytical_procedures', label: 'Analytical procedures (3.2.S.4.2)', section: '3.2.S.4.2' },
  { value: 'method_validation', label: 'Method validation (3.2.S.4.3)', section: '3.2.S.4.3' },
  { value: 'batch_analyses', label: 'Batch analyses (3.2.S.4.4)', section: '3.2.S.4.4' },
  { value: 'justification_of_specification', label: 'Justification of specification (3.2.S.4.5)', section: '3.2.S.4.5' },
]

export default function Findings() {
  const [agent, setAgent] = useState<Agent>('evidence-rera')
  const [question, setQuestion] = useState('')
  const [section, setSection] = useState('3.2.S.4')
  const [topic, setTopic] = useState('general')
  const [findings, setFindings] = useState<Finding[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function run(e: FormEvent) {
    e.preventDefault()
    setError('')
    if (!question.trim()) { setError('Enter an assessment question.'); return }
    const req: AgentRequest = { ctd_section: section, assessment_question: question.trim() }
    if (agent === 's4-control') {
      req.ctd_section = S4_TOPICS.find(t => t.value === topic)?.section ?? '3.2.S.4'
      req.parameters = { topic }
    }
    setBusy(true)
    try {
      setFindings(await api.runAgent(agent, req))
    } catch (err) {
      setError((err as Error).message)
      setFindings(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <form className="card section-gap" onSubmit={run}>
        <div className="card-body form-grid">
          <div className="form-group form-full">
            <span className="field-label">Agent</span>
            <div className="segmented" role="radiogroup" aria-label="Agent">
              <button type="button" role="radio" aria-checked={agent === 'evidence-rera'}
                className={`btn ${agent === 'evidence-rera' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setAgent('evidence-rera')}>
                Evidence/RERA · find and cite
              </button>
              <button type="button" role="radio" aria-checked={agent === 's4-control'}
                className={`btn ${agent === 's4-control' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setAgent('s4-control')}>
                S.4 Control · specs and batches
              </button>
            </div>
          </div>

          <div className="form-group form-full">
            <label htmlFor="agent-question">Assessment question</label>
            <textarea id="agent-question" value={question} onChange={e => setQuestion(e.target.value)}
              placeholder="Enter an assessment question" />
          </div>

          {agent === 'evidence-rera' ? (
            <div className="form-group">
              <label htmlFor="agent-section">CTD section</label>
              <select id="agent-section" value={section} onChange={e => setSection(e.target.value)}>
                {CTD_SECTIONS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          ) : (
            <div className="form-group">
              <label htmlFor="agent-topic">S.4 topic</label>
              <select id="agent-topic" value={topic} onChange={e => setTopic(e.target.value)}>
                {S4_TOPICS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
          )}

          <div className="form-full row-actions">
            <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Running…' : 'Run agent'}</button>
          </div>
        </div>
      </form>

      {error && <div className="alert alert-error">{error}</div>}
      {findings && findings.length > 0 && (
        <WordToolbar onDownload={() => downloadFindingsReport(findings)}
          note="Saved assessor comments are included in red." />
      )}
      {findings?.map(f => <FindingCard key={f.finding_id} f={f} />)}
    </div>
  )
}

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

function FindingCard({ f }: { f: Finding }) {
  const rows = f.metadata.confidential_comparison_rows ?? []
  const flags = f.metadata.flags ?? []
  const weaker = f.metadata.below_threshold_candidates ?? []
  const agentLabel = f.agent_name === 'evidence_rera' ? 'Evidence/RERA' : 'S.4 Control'
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
                <thead><tr><th className="num">#</th><th>Source</th><th>Document</th><th>Version · date</th><th className="num">Page</th><th>CTD</th><th>Status</th></tr></thead>
                <tbody>
                  {f.citations.map((c, i) => (
                    <tr key={c.chunk_id}>
                      <td className="num" data-label="#">{i + 1}</td>
                      <td data-label="Source"><b>{c.issuing_organization}</b> · {c.source_title}</td>
                      <td data-label="Document">{c.source_identifier}</td>
                      <td data-label="Version">{citationDetails(c)}</td>
                      <td className="num" data-label="Page">{c.page_number ?? 'n/a'}</td>
                      <td data-label="CTD">{c.ctd_section ?? 'n/a'}</td>
                      <td data-label="Status">
                        <StatusPill status={c.applicability_status} />
                        {!c.provenance_complete && <> <span className="pill pill-yellow" title={c.missing_provenance.join(', ')}>incomplete</span></>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="text-muted">No citations: no passage met the evidence threshold.</p>}
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
