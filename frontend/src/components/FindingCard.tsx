import { useState, useEffect } from 'react'
import type {
  Finding,
  AssessorDecision,
  PendingDecision,
  S5Claim,
  S5Finding,
  S5AssessmentReport,
} from '../types'
import QAStatusBadge from './QAStatusBadge'
import S5AssessmentPanel from './S5AssessmentPanel'
import { assessS5Claim } from '../api'

interface Props {
  finding: Finding
  onDecisionSubmit: (findingId: string, pending: PendingDecision) => void
  submitError: string | null
  /** Present only for 3.2.S.5 findings. Triggers the POST /s5/assess call. */
  s5Claim?: S5Claim | null
}

const DECISIONS: AssessorDecision[] = ['Approve', 'Query', 'Reject']

type S5AssessState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'done'; result: S5Finding; assessmentReport: S5AssessmentReport }
  | { status: 'error'; message: string }

// ── Main component ───────────────────────────────────────────────────────────

export default function FindingCard({ finding, onDecisionSubmit, submitError, s5Claim }: Props) {
  const [pending, setPending] = useState<PendingDecision>({
    decision: null,
    disposition_note: '',
  })
  const [submitted, setSubmitted] = useState(false)
  const [s5Assess, setS5Assess] = useState<S5AssessState>({ status: 'idle' })
  // Phase 5: opt-in AI commentary (Ollama LLM) — default OFF so assessors
  // are not affected unless they explicitly request it.
  const [ollamaEnabled, setOllamaEnabled] = useState(false)
  const [ollamaLoading, setOllamaLoading] = useState(false)
  const [ollamaUnavailable, setOllamaUnavailable] = useState(false)
  const [commentaryAssessment, setCommentaryAssessment] =
    useState<Extract<S5AssessState, { status: 'done' }> | null>(null)
  const displayedAssessment = commentaryAssessment ?? s5Assess
  const [traceOpen, setTraceOpen] = useState(false)

  const uncertaintyColour =
    finding.uncertainty_score <= 30
      ? 'var(--colour-pass)'
      : finding.uncertainty_score <= 60
        ? 'var(--colour-flag)'
        : 'var(--colour-escalate)'

  function handleSubmit() {
    if (!pending.decision) return
    onDecisionSubmit(finding.finding_id, pending)
    setSubmitted(true)
  }

  useEffect(() => {
    if (submitted && !finding.assessor_decision && submitError) {
      setSubmitted(false)
    }
  }, [submitted, finding.assessor_decision, submitError])

  // Phase 2: use assessS5Claim (POST /s5/assess) so the returned finding
  // is already QA-stamped and the full 8-criterion assessment report is available.
  useEffect(() => {
    setCommentaryAssessment(null)
    setOllamaEnabled(false)
    setOllamaUnavailable(false)
    if (!s5Claim) return
    setS5Assess({ status: 'loading' })
    assessS5Claim(s5Claim)
      .then((response) =>
        setS5Assess({
          status: 'done',
          result: response.s5_finding,
          assessmentReport: response.assessment_report,
        })
      )
      .catch((err: unknown) =>
        setS5Assess({
          status: 'error',
          message: err instanceof Error ? err.message : 'S.5 assessment failed',
        }),
      )
  }, [s5Claim])

  // Phase 5: when assessor enables AI commentary, re-call /s5/assess with
  // ollama_enabled=true.  The returned finding may include model_review which
  // S5AssessmentPanel already renders via ModelReviewCollapsible.
  const handleOllamaToggle = () => {
    if (!s5Claim || s5Assess.status !== 'done') return
    const next = !ollamaEnabled
    setOllamaEnabled(next)
    setOllamaUnavailable(false)
    if (!next) {
      setCommentaryAssessment(null)
      return
    }
    setOllamaLoading(true)
    assessS5Claim(s5Claim, true)
      .then((response) => {
        if (!response.s5_finding.model_review) {
          setOllamaEnabled(false)
          setOllamaUnavailable(true)
          return
        }
        setCommentaryAssessment({
          status: 'done',
          result: response.s5_finding,
          assessmentReport: response.assessment_report,
        })
      })
      .catch(() => {
        setOllamaEnabled(false)
        setOllamaUnavailable(true)
      })
      .finally(() => setOllamaLoading(false))
  }

  const effectiveDecision = finding.assessor_decision ?? (submitted ? pending.decision : null)
  const isS5 = !!s5Claim

  return (
    <article className="finding-card" aria-label={`Finding ${finding.finding_id}`}>
      <header className="finding-card__header">
        <span className="finding-card__id">{finding.finding_id}</span>
        <div className="finding-card__qa-label">
          <span className="label-hint">AI QA status</span>
          <QAStatusBadge status={finding.qa_status} />
        </div>
      </header>

      {/* ── 3.2.S.5 findings: IPRP structured panel ── */}
      {isS5 && (
        <>
          {s5Assess.status === 'loading' && (
            <div className="finding-card__s5-loading">
              <p className="s5-loading">Checking reference standard against IPRP S.5 criteria…</p>
            </div>
          )}

          {s5Assess.status === 'error' && (
            <div className="finding-card__s5-error">
              <p className="s5-error" role="alert">
                S.5 assessment unavailable: {s5Assess.message}
              </p>
              {/* Fallback: show traceability fields so assessor is not left with nothing */}
              <section className="finding-card__ai-section" aria-label="AI assessment (fallback)">
                <h3 className="section-heading">AI Assessment</h3>
                <dl className="finding-card__fields">
                  <dt>Rationale</dt>
                  <dd>{finding.rationale}</dd>
                  <dt>Evidence</dt>
                  <dd className="evidence-snippet">"{finding.evidence_snippet}"</dd>
                  <dt>Citation</dt>
                  <dd>
                    {finding.citation
                      ? <span className="citation">{finding.citation}</span>
                      : <span className="citation citation--missing" role="alert">No citation provided</span>
                    }
                  </dd>
                </dl>
              </section>
            </div>
          )}

          {s5Assess.status === 'done' && (
            <>
              {/* Phase 5 — opt-in AI commentary toggle */}
              <div className="finding-card__ollama-toggle">
                <label className="ollama-toggle__label">
                  <input
                    type="checkbox"
                    className="ollama-toggle__checkbox"
                    checked={ollamaEnabled}
                    disabled={ollamaLoading}
                    onChange={handleOllamaToggle}
                    aria-label="Request AI commentary from local Ollama model"
                  />
                  <span className="ollama-toggle__text">
                    {ollamaLoading ? 'Requesting AI commentary…' : 'Request AI commentary (experimental)'}
                  </span>
                </label>
                <p className="ollama-toggle__disclaimer">
                  AI commentary is generated by a local language model and must not be
                  treated as a regulatory decision. Assessor judgement remains required.
                </p>
                {ollamaUnavailable && (
                  <p role="status">AI commentary is unavailable. The standard assessment is shown.</p>
                )}
              </div>
              {displayedAssessment.status === 'done' && (
                <S5AssessmentPanel
                  finding={finding}
                  claim={s5Claim!}
                  result={displayedAssessment.result}
                  assessmentReport={displayedAssessment.assessmentReport}
                />
              )}
            </>
          )}
        </>
      )}

      {/* ── Non-S5 findings: QA information with collapsible traceability ── */}
      {!isS5 && (
        <section className="finding-card__qa-section" aria-label="QA review">
          <h3 className="section-heading">QA Review</h3>

          <dl className="finding-card__fields">
            {finding.rule_references.length > 0 && (
              <>
                <dt>Rule references</dt>
                <dd>
                  <ul className="finding-card__rule-list">
                    {finding.rule_references.map((r) => (
                      <li key={r} className="finding-card__rule-item">{r}</li>
                    ))}
                  </ul>
                </dd>
              </>
            )}
          </dl>

          {/* Collapsible internal traceability */}
          <div className="finding-card__traceability">
            <button
              type="button"
              className="finding-card__traceability-toggle"
              onClick={() => setTraceOpen((v) => !v)}
              aria-expanded={traceOpen}
            >
              <span>Internal traceability (rationale, evidence, citation)</span>
              <span aria-hidden="true">{traceOpen ? '▲' : '▼'}</span>
            </button>

            {traceOpen && (
              <dl className="finding-card__traceability-body">
                <dt>Rationale</dt>
                <dd>{finding.rationale}</dd>

                <dt>Evidence</dt>
                <dd className="evidence-snippet">"{finding.evidence_snippet}"</dd>

                <dt>Citation</dt>
                <dd>
                  {finding.citation
                    ? <span className="citation">{finding.citation}</span>
                    : <span className="citation citation--missing" role="alert">No citation provided</span>
                  }
                </dd>

                <dt>Uncertainty</dt>
                <dd>
                  <div className="uncertainty-bar" aria-label={`Uncertainty score: ${finding.uncertainty_score} out of 100`}>
                    <div
                      className="uncertainty-bar__fill"
                      style={{ width: `${finding.uncertainty_score}%`, backgroundColor: uncertaintyColour }}
                    />
                  </div>
                  <span className="uncertainty-value">{finding.uncertainty_score} / 100</span>
                </dd>
              </dl>
            )}
          </div>
        </section>
      )}

      {/* ── Section E: Human assessor decision (all findings) ── */}
      <section className="finding-card__decision-section" aria-label="Assessor decision">
        <h3 className="section-heading">
          <span className="s5panel__section-label">E</span>
          Assessor Decision
        </h3>

        {effectiveDecision ? (
          <div className="decision-recorded">
            <span className={`decision-badge decision-badge--${effectiveDecision.toLowerCase()}`}>
              {effectiveDecision}
            </span>
            {(finding.disposition_note || pending.disposition_note) && (
              <p className="disposition-note">
                {finding.disposition_note ?? pending.disposition_note}
              </p>
            )}
            <p className="decision-timestamp">
              Recorded: {finding.decision_timestamp ?? new Date().toISOString()}
            </p>
          </div>
        ) : (
          <>
            <p className="decision-prompt">
              Select a decision. No option is pre-selected.
            </p>
            <div className="decision-buttons" role="group" aria-label="Decision options">
              {DECISIONS.map((d) => (
                <button
                  key={d}
                  type="button"
                  className={`decision-btn decision-btn--${d.toLowerCase()}${pending.decision === d ? ' decision-btn--selected' : ''}`}
                  onClick={() => setPending((p) => ({ ...p, decision: d }))}
                  aria-pressed={pending.decision === d}
                >
                  {d}
                </button>
              ))}
            </div>

            <label className="disposition-label" htmlFor={`note-${finding.finding_id}`}>
              Disposition note (optional)
            </label>
            <textarea
              id={`note-${finding.finding_id}`}
              className="disposition-textarea"
              rows={3}
              value={pending.disposition_note}
              onChange={(e) => setPending((p) => ({ ...p, disposition_note: e.target.value }))}
              placeholder="Enter any remarks for this finding…"
            />

            {submitError && (
              <p className="submit-error" role="alert">
                Decision could not be saved: {submitError}. Please try again.
              </p>
            )}

            <button
              type="button"
              className="submit-btn"
              disabled={!pending.decision}
              onClick={handleSubmit}
            >
              Record Decision
            </button>
          </>
        )}
      </section>
    </article>
  )
}
