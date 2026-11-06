import type { FormEvent } from 'react'
import { useState } from 'react'
import { api, CTD_SECTIONS } from '../api'
import type { AgentRequest, ComparisonRow, Finding } from '../types'
import { PassageCard, QaPill, sourceLabel } from './shared'

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
  const [s4Data, setS4Data] = useState('')
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
      if (s4Data.trim()) {
        try {
          const parsed = JSON.parse(s4Data)
          req.parameters = { topic, ...parsed }
        } catch {
          setError('The structured S.4 data is not valid JSON.')
          return
        }
      }
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
            <>
              <div className="form-group">
                <label htmlFor="agent-topic">S.4 topic</label>
                <select id="agent-topic" value={topic} onChange={e => setTopic(e.target.value)}>
                  {S4_TOPICS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
              <div className="form-group form-full">
                <label htmlFor="agent-s4data">Structured S.4 data (optional, JSON)</label>
                <textarea id="agent-s4data" className="text-mono" value={s4Data} onChange={e => setS4Data(e.target.value)} style={{ minHeight: 140 }}
                  placeholder='Paste structured S.4 data JSON here' />
              </div>
            </>
          )}

          <div className="form-full row-actions">
            <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Running…' : 'Run agent'}</button>
          </div>
        </div>
      </form>

      {error && <div className="alert alert-error">{error}</div>}
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

function FindingCard({ f }: { f: Finding }) {
  const rows = f.metadata.confidential_comparison_rows ?? []
  const flags = f.metadata.flags ?? []
  return (
    <div className="card section-gap finding">
      <div className="card-header">
        <span className="card-title">{f.agent_name === 'evidence_rera' ? 'Evidence/RERA' : 'S.4 Control'} · CTD {f.ctd_section}</span>
        <span className="row-actions"><QaPill status={f.qa_status} /><span className="pill pill-gray">{f.evidence_status.replace(/_/g, ' ')}</span></span>
      </div>
      <div className="card-body stack">
        <div>
          <div className="field-label">Conclusion</div>
          <p className="finding-conclusion">{f.conclusion}</p>
        </div>
        <div className="two-col">
          <div><div className="field-label">Rationale</div><p>{f.rationale}</p></div>
          <div><div className="field-label">Uncertainty</div><p>{f.uncertainty}</p></div>
        </div>
        {flags.length > 0 && (
          <div className="row-actions" style={{ flexWrap: 'wrap' }}>
            {flags.map(fl => <span key={fl} className="pill pill-yellow">{FLAG_TEXT[fl] ?? fl}</span>)}
          </div>
        )}

        {rows.length > 0 && (
          <div>
            <div className="field-label">Comparison rows</div>
            <div className="table-wrap">
              <table className="table-stack">
                <thead><tr><th>Test</th><th>Batch</th><th>Reported</th><th>Criterion</th><th>Outcome</th><th>Reason</th></tr></thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      <td data-label="Test">{r.test_name}</td>
                      <td className="text-mono" data-label="Batch">{r.batch_id ?? 'n/a'}</td>
                      <td className="text-mono" data-label="Reported">{r.reported_value} {r.reported_unit}</td>
                      <td className="text-mono" data-label="Criterion">{r.criterion_text ?? 'n/a'}</td>
                      <td data-label="Outcome"><span className={`pill ${OUTCOME[r.outcome].cls}`}>{OUTCOME[r.outcome].label}</span>{r.borderline && <> <span className="pill pill-yellow">borderline</span></>}</td>
                      <td className="text-muted" data-label="Reason">{r.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {f.citations.length > 0 && (
          <div>
            <div className="field-label">Citations</div>
            <ol className="citations">
              {f.citations.map(c => (
                <li key={c.chunk_id}>
                  {sourceLabel(c)} <span className="text-muted text-mono">· {c.source_identifier} · {c.chunk_id}</span>
                  {!c.provenance_complete && <span className="pill pill-yellow">missing {c.missing_provenance.join(', ')}</span>}
                </li>
              ))}
            </ol>
          </div>
        )}

        {f.regulatory_evidence.length > 0 && (
          <details>
            <summary>Show the {f.regulatory_evidence.length} supporting passage(s)</summary>
            <div className="stack" style={{ marginTop: 12 }}>
              {f.regulatory_evidence.map(p => <PassageCard key={p.chunk_id} p={p} />)}
            </div>
          </details>
        )}

        {(f.metadata.below_threshold_candidates?.length ?? 0) > 0 && (
          <details>
            <summary>{f.metadata.below_threshold_candidates!.length} weaker candidate(s) not used as evidence</summary>
            <ul className="citations">
              {f.metadata.below_threshold_candidates!.map(c => <li key={c.chunk_id}>{c.source} <span className="text-mono text-muted">· {c.chunk_id}</span></li>)}
            </ul>
          </details>
        )}

        <p className="text-muted text-mono">{f.finding_id} · {new Date(f.created_at).toLocaleString()}</p>
      </div>
    </div>
  )
}
