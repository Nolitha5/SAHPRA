import type { Finding, PendingDecision } from '../types'
import FindingCard from './FindingCard'

interface Props {
  section: string
  findings: Finding[]
  onDecisionSubmit: (findingId: string, pending: PendingDecision) => void
}

export default function SectionGroup({ section, findings, onDecisionSubmit }: Props) {
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
          <FindingCard key={f.finding_id} finding={f} onDecisionSubmit={onDecisionSubmit} />
        ))}
      </div>
    </section>
  )
}
