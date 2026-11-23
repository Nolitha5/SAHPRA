/**
 * API client for the SAHPRA M5 backend.
 *
 * BASE_URL defaults to http://localhost:8000.
 * Override with VITE_API_URL in a .env.local file if needed.
 */

import type { Finding, AssessorDecision, S5Claim, S5Finding, S5AssessEndpointResponse } from './types'

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText)
    throw new Error(`API ${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

/** Fetch QA-reviewed findings from the backend. */
export function fetchReviewedFindings(): Promise<Finding[]> {
  return request<Finding[]>('/findings/reviewed')
}

/** Check a sponsor's S.5 reference-standard claim. */
export function checkS5Claim(claim: S5Claim): Promise<S5Finding> {
  return request<S5Finding>('/s5/check', {
    method: 'POST',
    body: JSON.stringify(claim),
  })
}

/**
 * Integrated IPRP S.5 assessment (Phase 9).
 * Calls POST /s5/assess which runs check_s5_claim → review_s5_finding →
 * build_assessment_report and returns both the QA-stamped finding and the
 * 8-criterion structured assessment report.
 *
 * @param ollamaEnabled  When true, appends ?ollama_enabled=true so the backend
 *   calls the local Ollama LLM for AI reasoning commentary.  Defaults to false.
 *   The model_review field on the returned S5Finding will be null when false,
 *   when Ollama is unreachable, or when the model returns unparseable output.
 */
export function assessS5Claim(
  claim: S5Claim,
  ollamaEnabled = false,
): Promise<S5AssessEndpointResponse> {
  const url = ollamaEnabled ? '/s5/assess?ollama_enabled=true' : '/s5/assess'
  return request<S5AssessEndpointResponse>(url, {
    method: 'POST',
    body: JSON.stringify(claim),
  })
}

export interface DecisionResponse {
  finding_id: string
  decision: string
  timestamp: string
  audit_stub: boolean
  audit_saved: boolean
  message: string
}

/**
 * Submit an assessor decision for a finding.
 * Returns the server's response which includes whether the stub audit log was written.
 * Does NOT confirm that M4's real audit service received the record.
 */
export function submitDecision(
  findingId: string,
  decision: AssessorDecision,
  dispositionNote: string,
): Promise<DecisionResponse> {
  return request<DecisionResponse>(`/decisions/${findingId}`, {
    method: 'POST',
    body: JSON.stringify({
      finding_id: findingId,
      decision,
      disposition_note: dispositionNote || null,
    }),
  })
}
