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
  /**
   * Labels of QA rules that fired on this finding, e.g. ["R1:missing_citation"].
   * Empty array = all rules passed.  Set by the QA/Critic; never set by the UI.
   */
  rule_references: string[]
  assessor_decision: AssessorDecision | null
  disposition_note: string | null
  decision_timestamp: string | null
}

/** State managed locally in the UI for an in-progress assessor decision */
export interface PendingDecision {
  decision: AssessorDecision | null
  disposition_note: string
}

// ── S.5 Reference Standards types ──────────────────────────────────────────
// Mirror the Pydantic models in backend/models.py exactly.
// Field names use snake_case to match the JSON the backend returns.

/**
 * Type of reference standard used.
 *
 * Original values (Phase 0, retained for backward compatibility):
 *   compendial, in-house, other
 *
 * V2 additions (Phase 1):
 *   compendial_primary, in_house_primary, secondary_working, impurity, unknown
 */
export type ReferenceStandardType =
  | 'compendial'
  | 'in-house'
  | 'other'
  | 'compendial_primary'
  | 'in_house_primary'
  | 'secondary_working'
  | 'impurity'
  | 'unknown'

export type S5Verdict = 'COMPLIANT' | 'NON_COMPLIANT' | 'NEEDS_REVIEW'

// ── V2 Phase 2: new structured objects ──────────────────────────────────────

/**
 * Structured purity assignment for a reference standard (V2 Phase 2).
 * Ph. Eur. 5.12 §4-2-3: required when a CRS is used for quantitative analysis.
 */
export interface PurityAssignment {
  method: string              // e.g. "mass balance", "qNMR"
  value_percent?: number | null
  source: string              // e.g. "USP CoA Lot R09060"
  is_traceable: boolean
}

/**
 * Official pharmacopoeial designation as stated in the dossier (V2 Phase 2).
 */
export interface OfficialStandardDesignation {
  designation_text: string    // e.g. "Amlodipine Besylate CRS"
  pharmacopoeia: string       // e.g. "USP", "BP", "Ph.Eur."
  edition: string             // e.g. "USP 47"
  is_verified: boolean
}

/**
 * Batch validity statement linking the RS lot to a tested product batch
 * (V2 Phase 2 — BVS concept from V2 Section 7).
 */
export interface BatchValidityStatement {
  batch_number: string
  validity_statement: string
  reference_standard_lot?: string | null
  is_cross_referenced: boolean
}

/**
 * One named impurity reference standard (V2 Phase 2 restructured).
 *
 * Breaking change from Phase 0:
 *   official_name  — was 'name'
 *   purity_percent — was 'purity_assigned: boolean'
 * New fields: coa_available, is_primary
 */
export interface ImpurityStandard {
  official_name: string
  source: string
  purity_percent?: number | null
  coa_available?: boolean | null
  is_primary: boolean
  characterisation_methods: string[]
}

/**
 * Structured S.5 sponsor claim — sent to POST /s5/check.
 * Groups the four IPRP QAR sub-items (a)–(d) plus impurity standards.
 * Optional fields correspond to fields the applicant may have omitted.
 */
export interface S5Claim {
  // Core (always required)
  substance_name: string
  standard: string            // e.g. "USP", "BP", "Ph.Eur.", "IP"
  edition_claimed: string | null  // e.g. "USP 47", "BP 2024" — null when not yet stated
  submission_date: string | null  // ISO date string, e.g. "2024-03-01" — null when not yet stated
  test_method?: string | null

  // Sub-item (a): Primary reference standard
  standard_type?: ReferenceStandardType | null
  lot_number?: string | null

  // In-house primary only
  inhouse_characterisation_methods?: string[] | null
  inhouse_purity_assigned?: boolean | null
  inhouse_coa_submitted?: boolean | null

  // Sub-item (b): CoA + overlaid IR spectra
  coa_submitted?: boolean | null
  ir_spectra_submitted?: boolean | null

  // Sub-item (c): Secondary / working standard
  working_standard_lot?: string | null
  working_standard_source?: string | null
  working_standard_assay?: number | null
  working_std_qualified_against_primary?: boolean | null

  // Sub-item (d): Source of reference standards for testing
  reference_standard_source_detail?: string | null
  ph_eur_used_for_content?: boolean | null

  // V2 Phase 1: declared use cases of the reference standard
  intended_use?: string[] | null

  // V2 Phase 2: structured objects
  purity_assignment?: PurityAssignment | null
  official_standard_designation?: OfficialStandardDesignation | null
  batch_validity_statement?: BatchValidityStatement | null

  // Impurity standards
  impurity_standards?: ImpurityStandard[] | null
}

// ── Phase 5: Ollama LLM reasoning commentary ─────────────────────────────────

/**
 * AI-generated reasoning commentary from the local Ollama LLM (Phase 5).
 *
 * ⚠ THIS IS NOT A REGULATORY DECISION. ⚠
 * This output is generated by a local language model and is provided solely
 * to support the human assessor's review.  It must not be treated as a QA
 * verdict, a compliance determination, or a substitute for pharmacopoeial
 * verification.  The human assessor retains final decision-making authority.
 */
export interface ModelReview {
  /** Ollama model that produced this output, e.g. "llama3.2" */
  model_name: string
  /** ISO 8601 UTC timestamp of generation */
  generated_at: string
  /** Identified inconsistencies or gaps in the claim */
  potential_issues: string[]
  /** IPRP checklist items the LLM flagged as potentially absent */
  missing_info: string[]
  /** Claims that appear to lack supporting evidence */
  unsupported_conclusions: string[]
  /** Suggested questions for the applicant */
  assessor_questions: string[]
  /** Fixed warning text — always present */
  disclaimer: string
}

/**
 * Result of POST /s5/check.
 *
 * verdict:
 *   COMPLIANT     — claimed edition matches the current edition at submission date.
 *   NON_COMPLIANT — a current edition was found but differs from the claimed edition.
 *   NEEDS_REVIEW  — authoritative reference information was unavailable.
 *
 * completeness_flags: IPRP checklist fields missing from the claim.
 * source_note: always states whether reference data is real or mocked.
 */
export interface S5Finding {
  substance_name: string
  standard_claimed: string
  edition_claimed: string | null  // null when not stated in the claim
  monograph_name: string | null
  edition_current: string | null
  evidence: string
  citation: string | null
  verdict: S5Verdict
  verdict_reason: string
  source_note: string
  completeness_flags: string[]

  // V2 Phase 1 additions — all optional; null until populated by later phases
  /** IPRP criterion ID, e.g. "S5-QAR-01" through "S5-AS-08". */
  criterion_id?: string | null
  /** Whether this criterion applies: APPLICABLE | NOT_APPLICABLE | NOT_PROVIDED | UNCLEAR */
  applicability_status?: string | null
  /** Evidence classification: SUPPORTED | PARTIAL | CONFLICTING | INSUFFICIENT | NOT_VERIFIED */
  evidence_sufficiency?: string | null

  // Web-retrieval provenance fields (Fix 3 — synced to backend)
  source_url?: string | null
  retrieved_at?: string | null
  evidence_tier?: string | null
  content_verified?: boolean | null
  raw_excerpt?: string | null

  // QA/Critic fields populated by POST /s5/assess.
  qa_status?: QAStatus | null
  rule_references?: string[]

  // Phase 5: Ollama LLM reasoning commentary
  // null when ollama_enabled=false (default), Ollama is unavailable, or parse failed.
  // This field is NEVER used to set qa_status or verdict.
  model_review?: ModelReview | null
}

// ── Document store types ──────────────────────────────────────────────────────
// Mirror the backend DocumentRecord response from GET /documents.

/** A record returned by GET /documents listing all ingested source documents. */
export interface DocumentRecord {
  doc_id: string
  filename: string
  source_type: string
  section_count: number
}

// ── Phase 9: IPRP-aligned structured assessment types ────────────────────────

/**
 * Structured assessment result for one IPRP S.5 criterion.
 * criterion_id: S5-QAR-01..04, S5-AS-01..04
 */
export interface S5CriterionResult {
  criterion_id: string
  criterion_title: string
  /** APPLICABLE | NOT_APPLICABLE | NOT_PROVIDED | UNCLEAR */
  applicability: string
  extracted_info?: Record<string, unknown> | null
  supporting_documents: string[]
  regulatory_guidance: string
  assessment_finding?: string | null
  missing_info: string[]
  /** SUPPORTED | NOT_VERIFIED | NOT_APPLICABLE | MISSING */
  evidence_verification_status: string
  assessor_questions: string[]
}

export interface S5QAReviewSummary {
  qa_status?: 'PASS' | 'FLAG' | 'ESCALATE' | null
  rule_references: string[]
  gaps: string[]
}

export interface S5AssessmentReport {
  substance_name: string
  standard_claimed: string
  /** ISO 8601 UTC timestamp */
  generated_at: string
  source_note: string
  /** Always exactly 8 items in IPRP order */
  criteria: S5CriterionResult[]
  qa_review: S5QAReviewSummary
}

export interface S5AssessEndpointResponse {
  /** QA-stamped S5Finding (verdict, qa_status, rule_references populated) */
  s5_finding: S5Finding
  assessment_report: S5AssessmentReport
}
