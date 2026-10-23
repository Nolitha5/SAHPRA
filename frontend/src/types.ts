export type QAStatus = 'PASS' | 'FLAG' | 'ESCALATE'
export type AssessorDecision = 'Approve' | 'Query' | 'Reject'

export interface Finding {
  finding_id: string
  ctd_section: string
  rationale: string
  evidence_snippet: string
  /** Non-empty string = structurally present. Factual accuracy is NOT verified. */
  citation: string
  /** 0 = certain, 100 = maximally uncertain */
  uncertainty_score: number
  qa_status: QAStatus | null
  assessor_decision: AssessorDecision | null
  disposition_note: string | null
  decision_timestamp: string | null
}

/** State managed locally in the UI for an in-progress assessor decision */
export interface PendingDecision {
  decision: AssessorDecision | null
  disposition_note: string
}
