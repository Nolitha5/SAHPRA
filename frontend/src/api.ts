/**
 * API client for the SAHPRA M5 backend.
 *
 * BASE_URL defaults to http://localhost:8000.
 * Override with VITE_API_URL in a .env.local file if needed.
 */

import type { Finding, AssessorDecision } from './types'

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
