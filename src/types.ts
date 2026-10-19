// Mirrors member2-rag/app/schemas.py. Keep field names identical to the Python models.

export type QAStatus = 'verified' | 'partial' | 'unsupported' | 'conflicting' | 'human-review'
export type EvidenceStatus =
  | 'candidate_evidence_found'
  | 'empty_knowledge_base'
  | 'no_passages_retrieved'
  | 'retrieved_not_relevant'
  | 'not_applicable'

export interface PassageMetadata {
  chunk_id: string
  source_title: string
  issuing_organization: string
  source_identifier: string
  document_version: string | null
  publication_date: string | null
  effective_date: string | null
  page_number: number | null
  ctd_section: string | null
  document_type: string
  content_hash: string
  applicability_status: string
  chunk_index: number | null
  chunk_size: number | null
  chunk_overlap: number | null
  language: string | null
}

export interface StoredPassage {
  chunk_id: string
  text: string
  metadata: PassageMetadata
  provenance_complete: boolean
  missing_provenance: string[]
}

export interface PassagePage {
  total: number
  limit: number
  offset: number
  items: StoredPassage[]
}

export type Facets = Record<
  'issuing_organization' | 'ctd_section' | 'document_type' | 'applicability_status',
  Record<string, number>
>

export interface RetrievedPassage {
  chunk_id: string
  text: string
  metadata: PassageMetadata
  retrieval_method: 'vector_search' | 'direct_lookup'
  retrieval_score: number | null
  retrieval_rank: number | null
  rerank_score: number | null
  rerank_rank: number | null
  untrusted_content_flags: string[]
}

export interface SearchFilters {
  ctd_sections?: string[]
  include_parent_sections?: boolean
  document_types?: string[]
  issuing_organizations?: string[]
  applicability_statuses?: string[]
}

export interface RetrievalResult {
  query_fingerprint: string
  filters: SearchFilters
  knowledge_base_size: number
  candidates_considered: number
  reranked: boolean
  embedding_model: string
  reranker_model: string | null
  passages: RetrievedPassage[]
  latency_ms: number
}

export interface Citation {
  chunk_id: string
  source_title: string
  issuing_organization: string
  source_identifier: string
  document_version: string | null
  publication_date: string | null
  effective_date: string | null
  page_number: number | null
  ctd_section: string | null
  document_type: string
  applicability_status: string
  content_hash: string
  provenance_complete: boolean
  missing_provenance: string[]
}

export interface SponsorEvidence {
  evidence_id: string
  ctd_section?: string | null
  description?: string
  document_reference?: string | null
  content?: string | null
  confidential?: boolean
}

export interface ComparisonRow {
  comparison: 'batch_vs_sponsor_spec' | 'sponsor_spec_vs_regulatory'
  test_name: string
  batch_id: string | null
  reported_value: string | null
  reported_unit: string | null
  criterion_text: string | null
  criterion_unit: string | null
  citation_chunk_id: string | null
  outcome: 'within_criteria' | 'outside_criteria' | 'at_least_as_strict' | 'less_strict' | 'not_compared'
  reason: string
  borderline: boolean
}

export interface Finding {
  schema_version: string
  finding_id: string
  agent_name: string
  ctd_section: string
  assessment_question: string
  sponsor_evidence: SponsorEvidence[]
  regulatory_evidence: RetrievedPassage[]
  citations: Citation[]
  conclusion: string
  rationale: string
  uncertainty: string
  qa_status: QAStatus
  evidence_status: EvidenceStatus
  requires_human_review: boolean
  metadata: {
    flags?: string[]
    version_conflicts?: Record<string, string[]>
    s4_topic?: string
    comparison_counts?: Record<string, number>
    confidential_comparison_rows?: ComparisonRow[]
    below_threshold_candidates?: { chunk_id: string; source: string; retrieval_score: number | null; rerank_score: number | null }[]
    retrieval?: { knowledge_base_size: number; candidates_considered: number; reranked: boolean; latency_ms: number }
    [key: string]: unknown
  }
  created_at: string
}

export interface AgentRequest {
  ctd_section: string
  assessment_question: string
  sponsor_evidence?: SponsorEvidence[]
  filters?: SearchFilters | null
  parameters?: Record<string, unknown>
}

export interface PageRef {
  source_identifier: string
  page_number: number
}

export interface BenchmarkCase {
  question_id: string
  question: string
  ctd_section: string
  relevant_chunk_ids: string[]
  relevant_pages: PageRef[]
  reference_answer?: string | null
  expert_notes?: string | null
  labelled_by?: string | null
}

export interface BenchmarkRunSummary {
  name: string
  config: Record<string, unknown>
  knowledge_base_size: number
  queries_evaluated: number
  aggregate: Record<string, number>
  latency: Record<string, number>
  ragas: Record<string, number> | null
  checks: { missing_labelled_chunk_ids?: string[]; questions_found_verbatim_in_index?: string[] }
}

export interface BenchmarkResultFile {
  file: string
  created_at: string
  num_questions: number
  benchmark_sha256: string
  runs: BenchmarkRunSummary[]
}

export interface Health {
  status: string
  api_version: string
  knowledge_base_size: number
  collection: string
  embedding_model: string
  reranker_model: string | null
  candidate_k: number
  final_k: number
  editing_enabled: boolean
}

export interface ImportReport {
  source_file: string
  lines_read: number
  valid_records: number
  rejected: number
  rejected_details: { line_number: number; chunk_id: string | null; message: string }[]
  skipped_duplicates: number
  added: number
  updated: number
  unchanged: number
  total_in_collection: number
  dry_run: boolean
}
