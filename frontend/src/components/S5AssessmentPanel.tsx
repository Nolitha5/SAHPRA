/**
 * S5AssessmentPanel.tsx
 *
 * IPRP QWGG S.5 structured assessment panel.
 * Rendered by FindingCard for all CTD 3.2.S.5 findings that carry an S5Claim.
 *
 * Layout follows the IPRP S.5 four-point structure:
 *   Section A — Assessment Case Overview
 *   Section B — Information for Quality Assessment Report (reference standards tables)
 *   Section C — IPRP S.5 Assessment Points 1–4 (expandable)
 *   Section D — QA / Critic Review (flags, model review, traceability)
 *
 * Section E (Assessor Decision) stays in FindingCard and is NOT rendered here.
 *
 * Phase 2: when assessmentReport is provided (from POST /s5/assess), Section C
 * renders the backend's 8 IPRP-structured S5CriterionResult objects instead of
 * the frontend-constructed assessment points.  Sections A, B, D are unchanged.
 *
 * This panel displays regulatory-structured information for assessor review.
 * It does NOT make regulatory decisions. All fields are read-only.
 */

import { useState } from 'react'
import type {
  S5Claim,
  S5Finding,
  Finding,
  ModelReview,
  S5AssessmentReport,
  S5CriterionResult,
} from '../types'

interface Props {
  finding: Finding
  claim: S5Claim
  result: S5Finding
  /** Phase 2: IPRP 8-criterion structured report from POST /s5/assess. */
  assessmentReport?: S5AssessmentReport
}

function notProvided(label?: string) {
  return (
    <span className="s5panel__not-provided" aria-label={`${label ?? 'Value'} not provided`}>
      Not provided
    </span>
  )
}

function notApplicable() {
  return <span className="s5panel__not-applicable">Not applicable</span>
}

function bool(value: boolean | null | undefined, trueLabel = 'Yes', falseLabel = 'No') {
  if (value == null) return notProvided()
  return (
    <span className={value ? 's5panel__bool--yes' : 's5panel__bool--no'}>
      {value ? trueLabel : falseLabel}
    </span>
  )
}

function EvidenceTierBadge({ tier }: { tier: string | null | undefined }) {
  if (!tier) return null
  const cls = tier.startsWith('TIER_1') ? 'tier1' : tier.startsWith('TIER_2') ? 'tier2' : 'tier3'
  const label = tier.replace(/_/g, ' ')
  return (
    <span className={`s5panel__tier-badge s5panel__tier-badge--${cls}`} aria-label={`Evidence tier: ${label}`}>
      {label}
    </span>
  )
}

function EvidenceSufficiencyChip({ value }: { value: string | null | undefined }) {
  if (!value) return null
  const labels: Record<string, string> = {
    SUPPORTED: 'Supported', PARTIAL: 'Partial', CONFLICTING: 'Conflicting',
    INSUFFICIENT: 'Insufficient', NOT_VERIFIED: 'Not Verified',
  }
  const cls = value.toLowerCase().replace('_', '-')
  return (
    <span className={`s5panel__sufficiency s5panel__sufficiency--${cls}`}>
      {labels[value] ?? value}
    </span>
  )
}

function SectionA({ claim, result }: { claim: S5Claim; result: S5Finding }) {
  return (
    <section className="s5panel__section s5panel__section--a" aria-labelledby="s5-sec-a-heading">
      <h3 id="s5-sec-a-heading" className="s5panel__section-heading">
        <span className="s5panel__section-label">A</span>
        Assessment Case Overview
      </h3>
      <dl className="s5panel__overview-grid">
        <dt>Drug substance</dt>
        <dd>{result.substance_name || claim.substance_name}</dd>
        <dt>Pharmacopoeial standard</dt>
        <dd>
          {result.standard_claimed || claim.standard}
          {claim.official_standard_designation && (
            <span className="s5panel__secondary-text">
              {' '}&mdash; {claim.official_standard_designation.designation_text}
            </span>
          )}
        </dd>
        <dt>Edition claimed</dt>
        <dd>{result.edition_claimed || claim.edition_claimed}</dd>
        <dt>Current edition</dt>
        <dd>
          {result.edition_current ?? (
            <span className="s5panel__not-verified">Not confirmed</span>
          )}
        </dd>
        <dt>Submission date</dt>
        <dd>{claim.submission_date}</dd>
        <dt>CTD section</dt>
        <dd>3.2.S.5 &mdash; Reference Standards or Materials</dd>
        <dt>Assessment case reference</dt>
        <dd className="s5panel__not-provided-text">Not provided</dd>
        <dt>Applicant name</dt>
        <dd className="s5panel__not-provided-text">Not provided</dd>
        <dt>Evidence tier</dt>
        <dd>
          <EvidenceTierBadge tier={result.evidence_tier} />
          {!result.evidence_tier && notProvided('Evidence tier')}
        </dd>
        <dt>Content verified</dt>
        <dd>{bool(result.content_verified, 'Verified', 'Not verified')}</dd>
        <dt>Verdict</dt>
        <dd>
          <span
            className={`s5panel__verdict s5panel__verdict--${result.verdict.toLowerCase().replace('_', '-')}`}
            aria-label={`S.5 verdict: ${result.verdict}`}
          >
            {result.verdict.replace(/_/g, ' ')}
          </span>
          <EvidenceSufficiencyChip value={result.evidence_sufficiency} />
        </dd>
      </dl>
      {result.verdict_reason && (
        <p className="s5panel__verdict-reason">{result.verdict_reason}</p>
      )}
      <p className="s5panel__source-note">{result.source_note}</p>
    </section>
  )
}

function SectionB({ claim }: { claim: S5Claim }) {
  const isCompendial =
    claim.standard_type === 'compendial' || claim.standard_type === 'compendial_primary'

  return (
    <section className="s5panel__section s5panel__section--b" aria-labelledby="s5-sec-b-heading">
      <h3 id="s5-sec-b-heading" className="s5panel__section-heading">
        <span className="s5panel__section-label">B</span>
        Information for Quality Assessment Report
      </h3>

      <div className="s5panel__subsection">
        <h4 className="s5panel__subsection-heading">B1 &mdash; Reference Standards or Materials</h4>
        <table className="s5panel__table">
          <thead>
            <tr><th>Standard</th><th>Source</th><th>Type</th><th>Lot number</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>{claim.standard}</td>
              <td>{claim.reference_standard_source_detail ?? notProvided('Source')}</td>
              <td>{claim.standard_type ? claim.standard_type.replace(/_/g, ' ') : notProvided('Type')}</td>
              <td>{claim.lot_number ?? notProvided('Lot number')}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="s5panel__subsection">
        <h4 className="s5panel__subsection-heading">B2 &mdash; Primary Reference Standard</h4>
        <table className="s5panel__table">
          <thead>
            <tr><th>Standard name</th><th>Pharmacopoeia</th><th>Lot</th><th>CoA submitted</th><th>IR spectra submitted</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>{claim.official_standard_designation?.designation_text ?? `${claim.standard} RS`}</td>
              <td>{claim.standard}</td>
              <td>{claim.lot_number ?? notProvided('Lot')}</td>
              <td>{bool(claim.coa_submitted)}</td>
              <td>{bool(claim.ir_spectra_submitted)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="s5panel__subsection">
        <h4 className="s5panel__subsection-heading">B3 &mdash; In-house Primary Standard</h4>
        {isCompendial ? (
          <p className="s5panel__not-applicable-block">
            {notApplicable()} &mdash; compendial primary standard declared; no in-house primary characterisation required.
          </p>
        ) : (
          <dl className="s5panel__kv-list">
            <dt>Characterisation methods</dt>
            <dd>
              {claim.inhouse_characterisation_methods?.length
                ? claim.inhouse_characterisation_methods.join(', ')
                : notProvided('Characterisation methods')}
            </dd>
            <dt>Purity assigned</dt>
            <dd>{bool(claim.inhouse_purity_assigned)}</dd>
            <dt>CoA submitted</dt>
            <dd>{bool(claim.inhouse_coa_submitted)}</dd>
          </dl>
        )}
      </div>

      <div className="s5panel__subsection">
        <h4 className="s5panel__subsection-heading">B4 &mdash; Secondary / Working Standard</h4>
        {claim.working_standard_lot || claim.working_standard_source ? (
          <table className="s5panel__table">
            <thead>
              <tr><th>Lot</th><th>Source</th><th>Qualified against primary</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>{claim.working_standard_lot ?? notProvided('Lot')}</td>
                <td>{claim.working_standard_source ?? notProvided('Source')}</td>
                <td>{bool(claim.working_std_qualified_against_primary)}</td>
              </tr>
            </tbody>
          </table>
        ) : (
          <p className="s5panel__not-provided-block">
            {notProvided('Working standard information')} &mdash; no secondary/working standard declared.
          </p>
        )}
      </div>
    </section>
  )
}

// ── Section C: legacy frontend-constructed assessment points (fallback) ───────

interface AssessmentPoint {
  number: number
  title: string
  what: string
  applicantInfo: string
  regulatoryRef: string
  finding: string
  gaps: string[]
  source: string
}

function buildAssessmentPoints(claim: S5Claim, result: S5Finding): AssessmentPoint[] {
  return [
    {
      number: 1,
      title: 'Reference-standard sources and intended use',
      what: 'Identifies the pharmacopoeial body and intended analytical application of the reference standard.',
      applicantInfo:
        `Standard: ${claim.standard}${claim.edition_claimed ? ' ' + claim.edition_claimed : ''}. ` +
        (claim.reference_standard_source_detail
          ? `Source: ${claim.reference_standard_source_detail}.`
          : 'Source not declared.') +
        (claim.intended_use?.length
          ? ` Intended use(s): ${claim.intended_use.join(', ')}.`
          : ' Intended use not declared.'),
      regulatoryRef: 'IPRP QWGG S.5 §1 — Sources of reference standards and materials',
      finding: result.verdict_reason,
      gaps: result.completeness_flags.filter((f) =>
        ['reference_standard_source_detail', 'intended_use'].includes(f),
      ),
      source: result.source_note,
    },
    {
      number: 2,
      title: 'Primary reference standard',
      what: 'Verifies the edition, lot, CoA and IR identity confirmation for the compendial or in-house primary standard.',
      applicantInfo:
        `Type: ${claim.standard_type ?? 'not declared'}. ` +
        `Lot: ${claim.lot_number ?? 'not declared'}. ` +
        `CoA: ${claim.coa_submitted == null ? 'not stated' : claim.coa_submitted ? 'submitted' : 'not submitted'}. ` +
        `IR spectra: ${claim.ir_spectra_submitted == null ? 'not stated' : claim.ir_spectra_submitted ? 'submitted' : 'not submitted'}.`,
      regulatoryRef: 'IPRP QWGG S.5 §2 — Primary reference standard; IPRP QAR sub-items (a) and (b)',
      finding:
        result.edition_current
          ? `Current edition: ${result.edition_current}. Claimed: ${result.edition_claimed ?? 'not stated'}.`
          : 'Current edition could not be confirmed from ingested documents.',
      gaps: result.completeness_flags.filter((f) =>
        ['lot_number', 'coa_submitted', 'ir_spectra_submitted', 'standard_type'].includes(f),
      ),
      source: result.citation ?? result.source_note,
    },
    {
      number: 3,
      title: 'Secondary / working standard',
      what: 'Confirms whether the working standard was qualified against the primary standard, with lot and source documented.',
      applicantInfo:
        claim.working_standard_lot || claim.working_standard_source
          ? `Lot: ${claim.working_standard_lot ?? 'not stated'}. ` +
            `Source: ${claim.working_standard_source ?? 'not stated'}. ` +
            `Qualified against primary: ${
              claim.working_std_qualified_against_primary == null
                ? 'not stated'
                : claim.working_std_qualified_against_primary
                  ? 'Yes'
                  : 'No'
            }.`
          : 'No working standard information provided.',
      regulatoryRef: 'IPRP QWGG S.5 §3 — Secondary / working reference standard; IPRP QAR sub-item (c)',
      finding:
        claim.working_std_qualified_against_primary === true
          ? 'Working standard is documented as qualified against the primary standard.'
          : claim.working_std_qualified_against_primary === false
            ? 'Working standard qualification against primary standard not confirmed — manual verification required.'
            : 'Working standard qualification status not provided.',
      gaps: result.completeness_flags.filter((f) =>
        ['working_standard_lot', 'working_standard_source', 'working_std_qualified_against_primary'].includes(f),
      ),
      source: result.source_note,
    },
    {
      number: 4,
      title: 'Impurity reference standards',
      what: 'Checks that each named impurity standard is documented with source, purity and CoA where applicable.',
      applicantInfo:
        claim.impurity_standards?.length
          ? `${claim.impurity_standards.length} impurity standard(s) declared: ` +
            claim.impurity_standards
              .map(
                (s) =>
                  `${s.official_name} (source: ${s.source}, ` +
                  `purity: ${s.purity_percent != null ? `${s.purity_percent}%` : 'not stated'}, ` +
                  `CoA: ${s.coa_available == null ? 'not stated' : s.coa_available ? 'yes' : 'no'})`,
              )
              .join('; ') +
            '.'
          : 'No impurity standards declared.',
      regulatoryRef: 'IPRP QWGG S.5 §4 — Impurity reference standards',
      finding:
        claim.impurity_standards?.length
          ? 'Impurity standards declared — verify each CoA and purity assignment manually.'
          : 'No impurity standards declared — confirm whether the dossier requires any.',
      gaps: result.completeness_flags.filter((f) => f.includes('impurity')),
      source: result.source_note,
    },
  ]
}

function AssessmentPointRow({ point }: { point: AssessmentPoint }) {
  const [open, setOpen] = useState(false)
  const hasGaps = point.gaps.length > 0

  return (
    <div className={`s5panel__point${hasGaps ? ' s5panel__point--has-gaps' : ''}`}>
      <button
        type="button"
        className="s5panel__point-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={`s5-point-${point.number}-body`}
      >
        <span className="s5panel__point-number">Point {point.number}</span>
        <span className="s5panel__point-title">{point.title}</span>
        {hasGaps && (
          <span className="s5panel__point-gap-badge" aria-label={`${point.gaps.length} gap(s) identified`}>
            {point.gaps.length} gap{point.gaps.length > 1 ? 's' : ''}
          </span>
        )}
        <span className="s5panel__point-chevron" aria-hidden="true">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div id={`s5-point-${point.number}-body`} className="s5panel__point-body">
          <dl className="s5panel__point-fields">
            <dt>What is assessed</dt>
            <dd>{point.what}</dd>
            <dt>Applicant information</dt>
            <dd>{point.applicantInfo}</dd>
            <dt>Regulatory reference</dt>
            <dd className="s5panel__ref-text">{point.regulatoryRef}</dd>
            <dt>Finding</dt>
            <dd>{point.finding}</dd>
            {point.gaps.length > 0 && (
              <>
                <dt>Gaps identified</dt>
                <dd>
                  <ul className="s5panel__gap-list">
                    {point.gaps.map((g) => (
                      <li key={g} className="s5panel__gap-item">{g.replace(/_/g, ' ')}</li>
                    ))}
                  </ul>
                </dd>
              </>
            )}
            <dt>Supporting source</dt>
            <dd className="s5panel__source-text">{point.source}</dd>
          </dl>
        </div>
      )}
    </div>
  )
}

// ── Section C: Phase 2 — backend criterion row ────────────────────────────────

function applicabilityClass(applicability: string): string {
  switch (applicability) {
    case 'NOT_APPLICABLE': return 's5panel__point--not-applicable'
    case 'NOT_PROVIDED':   return 's5panel__point--not-provided'
    default:               return ''
  }
}

function evStatusClass(status: string): string {
  if (status === 'MISSING') return 's5panel__point--has-gaps'
  return ''
}

function CriterionRow({ criterion }: { criterion: S5CriterionResult }) {
  const [open, setOpen] = useState(false)
  const gapCount = criterion.missing_info.length
  const hasGaps = gapCount > 0
  const notApplicableOrNotProvided =
    criterion.applicability === 'NOT_APPLICABLE' || criterion.applicability === 'NOT_PROVIDED'

  const rowClass = [
    's5panel__point',
    hasGaps ? evStatusClass(criterion.evidence_verification_status) : '',
    notApplicableOrNotProvided ? applicabilityClass(criterion.applicability) : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <div className={rowClass}>
      <button
        type="button"
        className="s5panel__point-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls={`s5-crit-${criterion.criterion_id}-body`}
      >
        <span className="s5panel__point-number">{criterion.criterion_id}</span>
        <span className="s5panel__point-title">{criterion.criterion_title}</span>
        {hasGaps && (
          <span className="s5panel__point-gap-badge" aria-label={`${gapCount} gap(s) identified`}>
            {gapCount} gap{gapCount > 1 ? 's' : ''}
          </span>
        )}
        {notApplicableOrNotProvided && (
          <span className="s5panel__not-applicable" aria-label={criterion.applicability}>
            {criterion.applicability === 'NOT_APPLICABLE' ? 'N/A' : 'Not provided'}
          </span>
        )}
        <span className="s5panel__point-chevron" aria-hidden="true">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div id={`s5-crit-${criterion.criterion_id}-body`} className="s5panel__point-body">
          <dl className="s5panel__point-fields">
            <dt>Applicability</dt>
            <dd>{criterion.applicability.replace(/_/g, ' ')}</dd>

            <dt>Regulatory reference</dt>
            <dd className="s5panel__ref-text">{criterion.regulatory_guidance}</dd>

            {criterion.assessment_finding && (
              <>
                <dt>Assessment finding</dt>
                <dd>{criterion.assessment_finding}</dd>
              </>
            )}

            <dt>Evidence verification status</dt>
            <dd>
              <span className={`s5panel__ev-status s5panel__ev-status--${criterion.evidence_verification_status.toLowerCase().replace('_', '-')}`}>
                {criterion.evidence_verification_status.replace(/_/g, ' ')}
              </span>
            </dd>

            {criterion.supporting_documents && criterion.supporting_documents.length > 0 && (
              <>
                <dt>Supporting documents</dt>
                <dd>
                  <ul className="s5panel__gap-list s5panel__doc-list">
                    {criterion.supporting_documents.map((ref, i) => {
                      const [docId, sectionId] = ref.split(':');
                      return (
                        <li key={i} className="s5panel__doc-item">
                          <span className="s5panel__doc-id">{docId}</span>
                          {sectionId && (
                            <span className="s5panel__doc-section"> § {sectionId}</span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </dd>
              </>
            )}

            {criterion.missing_info.length > 0 && (
              <>
                <dt>Missing information</dt>
                <dd>
                  <ul className="s5panel__gap-list">
                    {criterion.missing_info.map((m, i) => (
                      <li key={i} className="s5panel__gap-item">{m}</li>
                    ))}
                  </ul>
                </dd>
              </>
            )}

            {criterion.assessor_questions.length > 0 && (
              <>
                <dt>Assessor questions</dt>
                <dd>
                  <ul className="s5panel__gap-list">
                    {criterion.assessor_questions.map((q, i) => (
                      <li key={i} className="s5panel__gap-item">{q}</li>
                    ))}
                  </ul>
                </dd>
              </>
            )}
          </dl>
        </div>
      )}
    </div>
  )
}

// ── Section C dispatcher ─────────────────────────────────────────────────────

function SectionC({
  claim,
  result,
  assessmentReport,
}: {
  claim: S5Claim
  result: S5Finding
  assessmentReport?: S5AssessmentReport
}) {
  // Phase 2: use backend criteria when available
  if (assessmentReport) {
    const totalGaps = assessmentReport.criteria.reduce(
      (acc, c) => acc + c.missing_info.length,
      0,
    )
    return (
      <section className="s5panel__section s5panel__section--c" aria-labelledby="s5-sec-c-heading">
        <h3 id="s5-sec-c-heading" className="s5panel__section-heading">
          <span className="s5panel__section-label">C</span>
          IPRP S.5 Assessment Points
          {totalGaps > 0 && (
            <span className="s5panel__flags-summary">
              {totalGaps} checklist gap{totalGaps > 1 ? 's' : ''}
            </span>
          )}
        </h3>
        <div className="s5panel__points-list">
          {assessmentReport.criteria.map((criterion) => (
            <CriterionRow key={criterion.criterion_id} criterion={criterion} />
          ))}
        </div>
      </section>
    )
  }

  // Fallback: frontend-constructed points (pre-Phase 2 / /s5/check path)
  const points = buildAssessmentPoints(claim, result)
  return (
    <section className="s5panel__section s5panel__section--c" aria-labelledby="s5-sec-c-heading">
      <h3 id="s5-sec-c-heading" className="s5panel__section-heading">
        <span className="s5panel__section-label">C</span>
        IPRP S.5 Assessment Points
        {result.completeness_flags.length > 0 && (
          <span className="s5panel__flags-summary">
            {result.completeness_flags.length} checklist gap{result.completeness_flags.length > 1 ? 's' : ''}
          </span>
        )}
      </h3>
      <div className="s5panel__points-list">
        {points.map((pt) => (
          <AssessmentPointRow key={pt.number} point={pt} />
        ))}
      </div>
    </section>
  )
}

function ModelReviewCollapsible({ review }: { review: ModelReview }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="s5panel__model-review">
      <button
        type="button"
        className="s5panel__model-review-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span>&#x1F916; AI Reasoning Commentary &mdash; {review.model_name}</span>
        <span aria-hidden="true">{open ? '▲' : '▼'}</span>
      </button>
      {open && (
        <div className="s5panel__model-review-body">
          <p className="s5panel__disclaimer" role="note">&#x26A0; {review.disclaimer}</p>
          <p className="s5panel__meta">
            Generated by <strong>{review.model_name}</strong> at{' '}
            {new Date(review.generated_at).toLocaleString()}
          </p>
          {review.potential_issues.length > 0 && (
            <div className="s5panel__review-group">
              <h5>Potential Issues</h5>
              <ul>{review.potential_issues.map((x, i) => <li key={i}>{x}</li>)}</ul>
            </div>
          )}
          {review.missing_info.length > 0 && (
            <div className="s5panel__review-group">
              <h5>Missing Information</h5>
              <ul>{review.missing_info.map((x, i) => <li key={i}>{x}</li>)}</ul>
            </div>
          )}
          {review.unsupported_conclusions.length > 0 && (
            <div className="s5panel__review-group">
              <h5>Unsupported Conclusions</h5>
              <ul>{review.unsupported_conclusions.map((x, i) => <li key={i}>{x}</li>)}</ul>
            </div>
          )}
          {review.assessor_questions.length > 0 && (
            <div className="s5panel__review-group">
              <h5>Suggested Assessor Questions</h5>
              <ul>{review.assessor_questions.map((x, i) => <li key={i}>{x}</li>)}</ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function SectionD({
  finding,
  result,
  assessmentReport,
}: {
  finding: Finding
  result: S5Finding
  assessmentReport?: S5AssessmentReport
}) {
  const [traceOpen, setTraceOpen] = useState(false)

  // Phase 2: QA gaps come from the backend report when available
  const backendGaps = assessmentReport?.qa_review.gaps ?? []
  const legacyFlags = result.completeness_flags

  return (
    <section className="s5panel__section s5panel__section--d" aria-labelledby="s5-sec-d-heading">
      <h3 id="s5-sec-d-heading" className="s5panel__section-heading">
        <span className="s5panel__section-label">D</span>
        QA / Critic Review
      </h3>

      <dl className="s5panel__kv-list">
        <dt>QA status</dt>
        <dd>
          {/* Phase 2: prefer qa_status from the QA-stamped s5_finding */}
          {result.qa_status ? (
            <span className={`qa-status-inline qa-status-inline--${result.qa_status.toLowerCase()}`}>
              {result.qa_status}
            </span>
          ) : finding.qa_status ? (
            <span className={`qa-status-inline qa-status-inline--${finding.qa_status.toLowerCase()}`}>
              {finding.qa_status}
            </span>
          ) : (
            <span className="s5panel__not-provided">Pending QA</span>
          )}
        </dd>

        {result.rule_references && result.rule_references.length > 0 && (
          <>
            <dt>Rule references</dt>
            <dd>
              <ul className="s5panel__rule-list">
                {result.rule_references.map((r) => (
                  <li key={r} className="s5panel__rule-item">{r}</li>
                ))}
              </ul>
            </dd>
          </>
        )}

        {/* Phase 2: show backend gaps if available, otherwise legacy flags */}
        {backendGaps.length > 0 ? (
          <>
            <dt>IPRP assessment gaps</dt>
            <dd>
              <ul className="s5panel__gap-list">
                {backendGaps.map((g, i) => (
                  <li key={i} className="s5panel__gap-item">{g}</li>
                ))}
              </ul>
            </dd>
          </>
        ) : legacyFlags.length > 0 ? (
          <>
            <dt>Missing IPRP checklist items</dt>
            <dd>
              <ul className="s5panel__gap-list">
                {legacyFlags.map((f) => (
                  <li key={f} className="s5panel__gap-item">{f.replace(/_/g, ' ')}</li>
                ))}
              </ul>
            </dd>
          </>
        ) : (
          <>
            <dt>Completeness</dt>
            <dd className="s5panel__complete">All IPRP checklist items accounted for.</dd>
          </>
        )}
      </dl>

      {result.model_review && <ModelReviewCollapsible review={result.model_review} />}

      <div className="s5panel__traceability">
        <button
          type="button"
          className="s5panel__traceability-toggle"
          onClick={() => setTraceOpen((v) => !v)}
          aria-expanded={traceOpen}
        >
          <span>Internal traceability</span>
          <span aria-hidden="true">{traceOpen ? '▲' : '▼'}</span>
        </button>
        {traceOpen && (
          <dl className="s5panel__traceability-body">
            <dt>Rationale</dt>
            <dd>{finding.rationale}</dd>
            <dt>Evidence snippet</dt>
            <dd className="s5panel__evidence-snippet">"{finding.evidence_snippet}"</dd>
            <dt>Citation</dt>
            <dd>
              {finding.citation
                ? <span>{finding.citation}</span>
                : <span className="s5panel__not-provided">No citation provided</span>
              }
            </dd>
            <dt>Uncertainty score</dt>
            <dd>
              {finding.uncertainty_score} / 100
              {result.criterion_id && (
                <span className="s5panel__secondary-text"> &middot; Criterion: {result.criterion_id}</span>
              )}
              {result.applicability_status && (
                <span className="s5panel__secondary-text"> &middot; {result.applicability_status}</span>
              )}
            </dd>
          </dl>
        )}
      </div>
    </section>
  )
}

export default function S5AssessmentPanel({ finding, claim, result, assessmentReport }: Props) {
  return (
    <div className="s5panel" aria-label="IPRP S.5 structured assessment">
      <SectionA claim={claim} result={result} />
      <SectionB claim={claim} />
      <SectionC claim={claim} result={result} assessmentReport={assessmentReport} />
      <SectionD finding={finding} result={result} assessmentReport={assessmentReport} />
    </div>
  )
}
