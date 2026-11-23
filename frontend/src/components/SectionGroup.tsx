import type { Finding, PendingDecision, S5Claim, DocumentRecord } from '../types'
import FindingCard from './FindingCard'

interface Props {
  section: string
  findings: Finding[]
  onDecisionSubmit: (findingId: string, pending: PendingDecision) => void
  submitErrors: Record<string, string>
  /**
   * Keyed by finding_id.  Present only when section === '3.2.S.5'.
   * Passed through to FindingCard so it can call POST /s5/check.
   */
  s5Claims?: Record<string, S5Claim>
  /** Ingested source documents — available for S.5 sections (currently passed through, not displayed inline). */
  documents?: DocumentRecord[]
}

export default function SectionGroup({ section, findings, onDecisionSubmit, submitErrors, s5Claims }: Props) {
  const flagCount = findings.filter(
    (f) => f.qa_status === 'FLAG' || f.qa_status === 'ESCALATE',
  ).length

  return (
    <section className="section-group" aria-label={`CTD section ${section}`}>
      <div className="section-group__header">
        <h2 className="section-group__title">CTD {section}</h2>
        <span className="section-group__meta">
          {findings.length} finding{findings.length !== 1 ? 's' : ''}
          {flagCount > 0 && (
            <span className="section-group__flag-count" role="alert">
              &nbsp;· {flagCount} flagged
            </span>
          )}
        </span>
      </div>
      <div className="section-group__findings">
        {findings.map((f) => (
          <FindingCard
            key={f.finding_id}
            finding={f}
            onDecisionSubmit={onDecisionSubmit}
            submitError={submitErrors[f.finding_id] ?? null}
            s5Claim={s5Claims?.[f.finding_id] ?? null}
          />
        ))}
      </div>
    </section>
  )
}
