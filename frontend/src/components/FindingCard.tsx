import { useState, useEffect } from 'react'
import type { Finding, AssessorDecision, PendingDecision } from '../types'
import QAStatusBadge from './QAStatusBadge'

interface Props {
  finding: Finding
  onDecisionSubmit: (findingId: string, pending: PendingDecision) => void
  submitError: string | null
}

const DECISIONS: AssessorDecision[] = ['Approve', 'Query', 'Reject']

export default function FindingCard({ finding, onDecisionSubmit, submitError }: Props) {
  const [pending, setPending] = useState<PendingDecision>({
    decision: null,
    disposition_note: '',
  })
  const [submitted, setSubmitted] = useState(false)

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

  // If App rolls back after a server error, submitted stays true but the finding
  // no longer carries an assessor_decision — reset so the assessor can retry.
  useEffect(() => {
    if (submitted && !finding.assessor_decision && submitError) {
      setSubmitted(false)
    }
  }, [submitted, finding.assessor_decision, submitError])

  const effectiveDecision = finding.assessor_decision ?? (submitted ? pending.decision : null)

  return (
    <article className="finding-card" aria-label={`Finding ${finding.finding_id}`}>
      <header className="finding-card__header">
        <span className="finding-card__id">{finding.finding_id}</span>
        {/* AI QA status — clearly labelled as system output */}
        <div className="finding-card__qa-label">
          <span className="label-hint">AI QA status</span>
          <QAStatusBadge status={finding.qa_status} />
        </div>
      </header>

      {/* AI assessment section */}
      <section className="finding-card__ai-section" aria-label="AI assessment">
        <h3 className="section-heading">AI Assessment</h3>

        <dl className="finding-card__fields">
          <dt>Rationale</dt>
          <dd>{finding.rationale}</dd>

          <dt>Evidence</dt>
          <dd className="evidence-snippet">"{finding.evidence_snippet}"</dd>

          <dt>Citation</dt>
          <dd>
            {finding.citation ? (
              <span className="citation">{finding.citation}</span>
            ) : (
              <span className="citation citation--missing" role="alert">
                No citation provided
              </span>
            )}
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
      </section>

      {/* Human assessor decision section — clearly separated */}
      <section className="finding-card__decision-section" aria-label="Assessor decision">
        <h3 className="section-heading">Assessor Decision</h3>

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
