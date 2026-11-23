import { useEffect, useState } from 'react'
import type { Finding, PendingDecision, S5Claim } from './types'
import SectionGroup from './components/SectionGroup'
import { fetchReviewedFindings, submitDecision } from './api'

function groupBySection(findings: Finding[]): Map<string, Finding[]> {
  const map = new Map<string, Finding[]>()
  for (const f of findings) {
    const group = map.get(f.ctd_section) ?? []
    group.push(f)
    map.set(f.ctd_section, group)
  }
  return map
}

type LoadState = 'loading' | 'ready' | 'error'

/**
 * Demo mock S5 claims keyed by finding_id.
 *
 * In production these would come from the sponsor's structured dossier data.
 * For the prototype, one representative claim is supplied per finding that
 * covers CTD section 3.2.S.5.  Findings not listed here will not trigger
 * the S.5 check panel.
 *
 * Fields correspond to the four IPRP QAR sub-items (a)–(d):
 *   (a) lot_number + standard_type
 *   (b) coa_submitted + ir_spectra_submitted
 *   (c) working_std_qualified_against_primary
 *   (d) reference_standard_source_detail
 */
const MOCK_S5_CLAIMS: Record<string, S5Claim> = {
  // F-003: Ethanol / BP 2019 claim — expected NON_COMPLIANT (outdated edition)
  // Data matches mock_findings.json finding F-003 exactly.
  'F-003': {
    substance_name: 'Ethanol',
    standard: 'BP',
    edition_claimed: 'BP 2019',
    submission_date: '2024-03-01',
    standard_type: 'compendial',
    lot_number: 'BP-ETH-2019-042',
    coa_submitted: true,
    ir_spectra_submitted: null,
    working_standard_lot: 'WS-ETH-LAB-001',
    working_standard_source: 'British Pharmacopoeia Commission',
    working_standard_assay: null,
    working_std_qualified_against_primary: true,
    reference_standard_source_detail: 'British Pharmacopoeia Commission',
  },
}

export default function App() {
  const [findings, setFindings] = useState<Finding[]>([])
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [loadError, setLoadError] = useState<string | null>(null)
  const [submitErrors, setSubmitErrors] = useState<Record<string, string>>({})
  useEffect(() => {
    fetchReviewedFindings()
      .then((data) => {
        setFindings(data)
        setLoadState('ready')
      })
      .catch((err: unknown) => {
        setLoadError(err instanceof Error ? err.message : 'Unknown error')
        setLoadState('error')
      })
  }, [])

  async function handleDecisionSubmit(findingId: string, pending: PendingDecision) {
    if (!pending.decision) return

    // Clear any previous error for this finding
    setSubmitErrors((prev) => { const next = { ...prev }; delete next[findingId]; return next })

    // Snapshot the finding's previous state so we can roll back on failure
    const previous = findings.find((f) => f.finding_id === findingId) ?? null

    // Optimistic UI update — record locally before the server confirms
    setFindings((prev) =>
      prev.map((f) =>
        f.finding_id === findingId
          ? {
              ...f,
              assessor_decision: pending.decision,
              disposition_note: pending.disposition_note || null,
              decision_timestamp: new Date().toISOString(),
            }
          : f,
      ),
    )

    try {
      const response = await submitDecision(findingId, pending.decision, pending.disposition_note)
      if (!response.audit_saved) {
        console.warn('[audit] stub write failed for', findingId)
      }
      // Sync timestamp from server
      setFindings((prev) =>
        prev.map((f) =>
          f.finding_id === findingId
            ? { ...f, decision_timestamp: response.timestamp }
            : f,
        ),
      )
    } catch (err) {
      console.error('[api] submitDecision failed', err)
      // Roll back optimistic update so the assessor can retry
      if (previous) {
        setFindings((prev) => prev.map((f) => f.finding_id === findingId ? previous : f))
      }
      setSubmitErrors((prev) => ({
        ...prev,
        [findingId]: err instanceof Error ? err.message : 'Unknown server error',
      }))
    }
  }

  const grouped = groupBySection(findings)
  const sections = Array.from(grouped.keys()).sort()

  const totalFlags = findings.filter(
    (f) => f.qa_status === 'FLAG' || f.qa_status === 'ESCALATE',
  ).length
  const decided = findings.filter((f) => f.assessor_decision !== null).length

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header__inner">
          <div>
            <h1 className="app-header__title">SAHPRA Assessor Interface</h1>
            <p className="app-header__subtitle">
              Module 3.2.S Drug Substance — Quality Assessment
            </p>
          </div>
          {loadState === 'ready' && (
            <div className="app-header__stats">
              <span>{findings.length} findings</span>
              {totalFlags > 0 && (
                <span className="stat--flagged">{totalFlags} flagged</span>
              )}
              <span>{decided} / {findings.length} decided</span>
            </div>
          )}
        </div>
      </header>

      <main className="app-main">
        {loadState === 'loading' && (
          <p className="status-message">Loading findings…</p>
        )}

        {loadState === 'error' && (
          <div className="error-banner" role="alert">
            <strong>Could not load findings.</strong>
            <p>{loadError}</p>
            <p className="error-hint">
              Make sure the backend is running:{' '}
              <code>uvicorn main:app --reload</code> in the{' '}
              <code>backend/</code> folder.
            </p>
          </div>
        )}

        {loadState === 'ready' && (
          <>
            <div className="notice">
              <strong>Note:</strong> AI QA status is system-generated and requires human
              review. All findings must be assessed by an authorised SAHPRA reviewer before
              a regulatory decision is recorded.
            </div>

            {sections.length === 0 ? (
              <p className="empty-state">No findings to display.</p>
            ) : (
              sections.map((section) => {
                // For 3.2.S.5 sections, build a claims map from the mock data.
                // Only findings that have a matching entry in MOCK_S5_CLAIMS
                const s5Claims =
                  section === '3.2.S.5'
                    ? Object.fromEntries(
                        (grouped.get(section) ?? [])
                          .filter((f) => f.finding_id in MOCK_S5_CLAIMS)
                          .map((f) => [f.finding_id, MOCK_S5_CLAIMS[f.finding_id]])
                      )
                    : undefined

                return (
                  <SectionGroup
                    key={section}
                    section={section}
                    findings={grouped.get(section)!}
                    onDecisionSubmit={handleDecisionSubmit}
                    submitErrors={submitErrors}
                    s5Claims={s5Claims}
                  />
                )
              })
            )}
          </>
        )}
      </main>
    </div>
  )
}
