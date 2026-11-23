from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel


class Finding(BaseModel):
    finding_id: str
    ctd_section: str  # e.g. "3.2.S.1", "3.2.S.5"
    rationale: str
    evidence_snippet: str
    # Structural presence is checked; factual accuracy is NOT verified here.
    citation: str
    # 0 = certain, 100 = maximally uncertain; range enforcement is done by QA/Critic
    uncertainty_score: int
    qa_status: Optional[Literal["PASS", "FLAG", "ESCALATE"]] = None
    # Rules that fired on this finding, e.g. ["R1:missing_citation", "R4:s5_missing_lot_number"].
    # Empty list means all rules passed.  Populated by the QA/Critic; never set by the UI.
    rule_references: list[str] = []
    assessor_decision: Optional[Literal["Approve", "Query", "Reject"]] = None
    disposition_note: Optional[str] = None
    decision_timestamp: Optional[datetime] = None


class AssessorDecisionRequest(BaseModel):
    finding_id: str
    decision: Literal["Approve", "Query", "Reject"]
    disposition_note: Optional[str] = None


# ── S.5 Reference Standards models ───────────────────────────────────────────
# Aligned with IPRP QWGG Guidance for Quality Assessors — Drug Substance,
# Section S.5 Reference Standards or Materials (page 17/22).
# Sub-items (a)–(d) map directly to the four checklist points in the QAR.


class ReferenceStandardType(str, Enum):
    """
    Type of reference standard used.

    Original values (retained for backward compatibility):
      COMPENDIAL — a compendial standard (USP, BP, Ph.Eur., IP).
                   IPRP: no further structural elucidation needed.
      IN_HOUSE   — an in-house primary standard.
                   IPRP: must be fully characterised.
      OTHER      — catch-all for non-compendial, non-in-house.

    V2 additions (Phase 1):
      COMPENDIAL_PRIMARY  — explicit primary compendial RS.
      IN_HOUSE_PRIMARY    — explicit primary in-house RS.
      SECONDARY_WORKING   — a secondary / working standard qualified against primary.
      IMPURITY            — a named impurity reference standard.
      UNKNOWN             — type not stated in the dossier.
    """
    COMPENDIAL         = "compendial"
    IN_HOUSE           = "in-house"
    OTHER              = "other"
    COMPENDIAL_PRIMARY = "compendial_primary"
    IN_HOUSE_PRIMARY   = "in_house_primary"
    SECONDARY_WORKING  = "secondary_working"
    IMPURITY           = "impurity"
    UNKNOWN            = "unknown"


class PurityAssignment(BaseModel):
    """
    Structured purity assignment for a reference standard (V2, Phase 2).

    Captures the method, numeric value and traceability of an assigned purity,
    as required by Ph. Eur. 5.12 §4-2-3 for CRS used in quantitative analysis
    and by IPRP for in-house primary standards.

    Fields:
      method        — e.g. "mass balance", "absolute purity (qNMR)", "titration"
      value_percent — numeric purity in percent, e.g. 99.5. None if not stated.
      source        — origin of the purity value, e.g. "USP CoA Lot R09060"
      is_traceable  — True when the value is traceable to an international
                      standard (SI, pharmacopoeial CRS); False for in-house
                      only assignments.
    """
    method: str
    value_percent: Optional[float] = None
    source: str
    is_traceable: bool = False


class OfficialStandardDesignation(BaseModel):
    """
    Structured capture of the official pharmacopoeial designation for a
    reference standard (V2, Phase 2).

    Ph. Eur. 5.12 / IPRP: the designation must unambiguously identify the
    standard, edition and issuing pharmacopoeia.

    Fields:
      designation_text — full official name as it appears on the label or
                         monograph, e.g. "Amlodipine Besylate CRS"
      pharmacopoeia    — issuing body, e.g. "USP", "BP", "Ph.Eur.", "IP"
      edition          — edition at time of submission, e.g. "USP 47"
      is_verified      — True when an authorised reviewer has confirmed the
                         designation against the primary source (usp.org, etc.)
                         Machine retrieval always leaves this False.
    """
    designation_text: str
    pharmacopoeia: str
    edition: str
    is_verified: bool = False


class BatchValidityStatement(BaseModel):
    """
    Cross-reference between the reference standard lot and the product batch
    for which it was used (V2, Phase 2 — BVS concept from V2 Section 7).

    IPRP requires traceability between the reference standard lot number and
    the specific product batch(es) it was used to test.

    Fields:
      batch_number           — product batch number being tested, e.g. "HDL-2024-001"
      validity_statement     — free-text validity statement as submitted by applicant
      reference_standard_lot — lot number of the RS used for this batch, e.g. "R09060"
      is_cross_referenced    — True when the RS lot is explicitly named in the
                               batch testing records; False when inferred only.
    """
    batch_number: str
    validity_statement: str
    reference_standard_lot: Optional[str] = None
    is_cross_referenced: bool = False


class ModelReview(BaseModel):
    """
    AI-generated reasoning commentary from the local Ollama LLM (Phase 5).

    ⚠ THIS IS NOT A REGULATORY DECISION. ⚠
    This output is generated by a local language model and is provided solely
    to support the human assessor's review.  It must not be treated as a QA
    verdict, a compliance determination, or a substitute for pharmacopoeial
    verification.  The human assessor retains final decision-making authority.

    Fields:
      model_name              — Ollama model that produced this output, e.g. "llama3.2"
      generated_at            — ISO 8601 UTC timestamp of generation
      potential_issues        — identified inconsistencies or gaps in the claim
      missing_info            — IPRP checklist items the LLM flagged as potentially absent
      unsupported_conclusions — claims that appear to lack supporting evidence
      assessor_questions      — suggested questions for the applicant
      disclaimer              — fixed warning text; always present
    """
    model_name: str
    generated_at: str                           # ISO 8601 UTC
    potential_issues: list[str] = []
    missing_info: list[str] = []
    unsupported_conclusions: list[str] = []
    assessor_questions: list[str] = []
    disclaimer: str = (
        "AI-generated reasoning only. "
        "Not a regulatory decision. "
        "Human assessor review required before any compliance determination is made."
    )


class ImpurityStandard(BaseModel):
    """
    One named impurity reference standard (V2 restructured, Phase 2).

    IPRP: characterisation + assigned purity required for each impurity standard.

    Changes from Phase 1 baseline:
      official_name  — renamed from 'name' (V2 alignment; more precise)
      purity_percent — replaces 'purity_assigned: bool' with a numeric value
                       (Optional; None when purity has not been assigned or stated)
      coa_available  — explicitly captures whether a CoA was submitted for this
                       impurity standard (IPRP sub-item b)
      is_primary     — True when this impurity standard is itself a primary
                       standard (not a secondary/working standard)
    """
    official_name: str                          # e.g. "Impurity-A", "Methyl ester analogue"
    source: str                                 # e.g. "ABC R&D Center (synthesised in-house)"
    purity_percent: Optional[float] = None      # Assigned purity %; None = not stated
    coa_available: Optional[bool] = None        # Was a CoA submitted? None = not stated
    is_primary: bool = False                    # Is this a primary impurity standard?
    characterisation_methods: list[str] = []    # e.g. ["IR", "NMR", "MS"]


class S5Claim(BaseModel):
    """
    Structured S.5 sponsor claim extracted from the dossier (supplied by M3).

    Fields are grouped by the four IPRP QAR sub-items:
      (a) Primary standard — pharmacopoeial / in-house, lot number
      (b) CoA + overlaid IR spectra
      (c) Secondary (working) standard traceability
      (d) Source of standards used for identification, purity, potency tests
    Plus impurity standards (IPRP: if applicable).

    Optional fields that are None indicate the applicant did not provide that
    information.  The QA/Critic treats systematically absent fields as a
    completeness failure (R7).
    """
    # ── Core (always required) ────────────────────────────────────────────
    substance_name: str
    standard: str                               # "USP", "BP", "Ph.Eur.", "IP"
    edition_claimed: Optional[str] = None       # e.g. "USP 47", "BP 2024" — None when not yet stated
    submission_date: Optional[date] = None      # ISO date — None when not yet stated
    test_method: Optional[str] = None           # e.g. "Purity by HPLC"

    # ── Sub-item (a): Primary reference standard ──────────────────────────
    # IPRP: "State the primary reference standard used: compendial or in-house;
    #         reference standard and batch number."
    standard_type: Optional[ReferenceStandardType] = None
    lot_number: Optional[str] = None            # e.g. "R09060"  (USP lot used in Amlodipine case)

    # In-house primary only:
    # IPRP: "If a primary in-house reference standard is used, state if it is
    #         fully characterised (e.g., IR, UV, NMR, MS). State if a certificate
    #         of analysis has been submitted with purity assigned based on mass
    #         balance or a determination of absolute purity."
    inhouse_characterisation_methods: Optional[list[str]] = None  # ["IR","UV","NMR","MS"]
    inhouse_purity_assigned: Optional[bool] = None
    inhouse_coa_submitted: Optional[bool] = None

    # ── Sub-item (b): CoA + overlaid IR spectra ───────────────────────────
    # IPRP / real dossier checklist point (b):
    # "State if a certificate of analysis and overlaid IR spectra have been submitted."
    coa_submitted: Optional[bool] = None
    ir_spectra_submitted: Optional[bool] = None

    # ── Sub-item (c): Secondary / working standard ────────────────────────
    # IPRP: "State if a secondary reference standard (e.g. working standard) is
    #         standardised against the compendial reference standard or primary
    #         reference standard."
    # Real dossier: WS no. HDL1/ABWS/20/1 qualified against USPRS Lot R09060.
    working_standard_lot: Optional[str] = None             # e.g. "HDL1/ABWS/20/1"
    working_standard_source: Optional[str] = None          # e.g. "ABC Unit-7"
    working_std_qualified_against_primary: Optional[bool] = None

    # ── Sub-item (d): Source of reference standards for testing ──────────
    # IPRP: "The source(s) of the reference standards or materials used in the
    #         testing of the drug substance (identification, purity, potency tests).
    #         If Ph.Eur. reference standard is used for quantitative analysis,
    #         it should be for content, not identity only."
    reference_standard_source_detail: Optional[str] = None  # e.g. "Purchased from USP"
    ph_eur_used_for_content: Optional[bool] = None           # Relevant only when standard=Ph.Eur.

    # ── Ph. Eur. 5.12 supplementary fields ───────────────────────────────
    # assigned_content: the numeric purity/content value stated on the CRS label
    #   (Ph. Eur. 5.12 §4-2-3).  Required when a Ph. Eur. CRS is used for
    #   quantitative analysis.  None = applicant did not provide this value.
    assigned_content: Optional[float] = None                 # e.g. 99.5 (percent)

    # working_standard_assay: the assigned purity (%) of the in-house working
    #   standard, derived from qualification against the primary standard
    #   (Ph. Eur. 5.12 §4-5).  None = not stated.
    working_standard_assay: Optional[float] = None           # e.g. 99.2 (percent)

    # ── V2 additions (Phase 1) ────────────────────────────────────────────
    # intended_use: declared use cases of the reference standard for this
    # submission, e.g. ["assay", "related_substances", "identification"].
    # None = applicant did not declare intended use.
    intended_use: Optional[list[str]] = None

    # ── V2 additions (Phase 2) ────────────────────────────────────────────
    # Structured purity assignment for the primary reference standard.
    # None = applicant did not provide structured purity data.
    purity_assignment: Optional[PurityAssignment] = None

    # Official pharmacopoeial designation as stated in the dossier.
    # None = applicant did not provide a structured designation.
    official_standard_designation: Optional[OfficialStandardDesignation] = None

    # Batch validity statement linking the RS lot to the tested product batch.
    # None = not provided or not applicable.
    batch_validity_statement: Optional[BatchValidityStatement] = None

    # ── Impurity standards ────────────────────────────────────────────────
    # IPRP: "Impurity standard (characterisation, purity), if applicable."
    impurity_standards: Optional[list[ImpurityStandard]] = None




class S5Finding(BaseModel):
    """
    Result of the S.5 Reference Standards check.

    verdict:
      COMPLIANT          — claimed edition matches the current edition at submission date.
      NON_COMPLIANT      — a current edition was found but differs from the claimed edition.
      NEEDS_REVIEW       — authoritative reference information was unavailable; no verdict made.

    completeness_flags:
      List of field names that are missing but required by IPRP.
      Empty list means the submission is structurally complete.

    source_note always states whether reference data is real or mocked.
    """
    substance_name: str
    standard_claimed: str
    edition_claimed: Optional[str] = None  # None when not stated in the claim
    monograph_name: Optional[str] = None
    edition_current: Optional[str] = None
    evidence: str
    citation: Optional[str] = None
    verdict: Literal["COMPLIANT", "NON_COMPLIANT", "NEEDS_REVIEW"]
    verdict_reason: str
    source_note: str
    # List of IPRP checklist items missing from the claim
    completeness_flags: list[str] = []

    # ── V2 additions (Phase 1) ────────────────────────────────────────────
    # criterion_id: the IPRP criterion this finding addresses, e.g. "S5-QAR-01"
    # through "S5-AS-08". None until criterion-level tracking is implemented.
    criterion_id: Optional[str] = None

    # applicability_status: whether the criterion applies to this submission.
    # Values: "APPLICABLE" | "NOT_APPLICABLE" | "NOT_PROVIDED" | "UNCLEAR"
    applicability_status: Optional[str] = None

    # evidence_sufficiency: V2 replaces raw uncertainty_score display with a
    # categorised classification derived from structured QA rule evaluation.
    # Values: "SUPPORTED" | "PARTIAL" | "CONFLICTING" | "INSUFFICIENT" | "NOT_VERIFIED"
    evidence_sufficiency: Optional[str] = None

    # ── Web-retrieval provenance fields (Fix 3) ───────────────────────────
    # Populated when retrieval_enabled=True is passed to check_s5_claim().
    # All Optional with None defaults so existing callers are unaffected.

    # URL of the primary source consulted (e.g. doi.org link from CrossRef).
    source_url: Optional[str] = None

    # ISO 8601 UTC timestamp of when retrieval was performed.
    retrieved_at: Optional[str] = None

    # Evidence tier constant from retrieval.py.
    evidence_tier: Optional[str] = None

    # False for all machine-retrieved records. A human reviewer sets this to
    # True after consulting the primary source directly (e.g. usp.org).
    content_verified: Optional[bool] = None

    # Short text excerpt from the retrieved source, if available.
    raw_excerpt: Optional[str] = None

    # ── QA/Critic review fields (Phase 6) ────────────────────────────────
    # Populated by review_s5_finding() in qa_critic.py.
    # None / empty until POST /s5/review is called on this finding.
    qa_status: Optional[Literal["PASS", "FLAG", "ESCALATE"]] = None
    rule_references: list[str] = []

    # ── Ollama LLM reasoning (Phase 5) ───────────────────────────────────
    # Populated when ollama_enabled=True is passed to check_s5_claim() AND
    # Ollama is reachable with a compatible model.
    # None when Ollama is not requested, not reachable, or returns invalid output.
    # This field is NEVER used to set qa_status or verdict.
    model_review: Optional[ModelReview] = None


# ── Phase 2: Document Ingestion models ───────────────────────────────────────
# These models support the document ingestion service (ingestor.py).
# They are data-only: no verdict, qa_status or evidence_sufficiency logic.


class DocumentSourceType(str, Enum):
    """
    Classification of an ingested source document.

    IPRP_GUIDANCE  — IPRP QWGG Guidance for Quality Assessors (SRC-IPRP-01).
    PHARMACOPOEIA  — Pharmacopoeial chapter, e.g. Ph. Eur. 5.12 (SRC-PEUR-01).
    V2_MAPPING     — M5 S.5 Requirement-to-Data Mapping V2 (internal spec).
    SCORE_REPORT   — SCoRE pilot assessment report (SRC-SCORE-01).
    APPLICANT_DOSSIER — Uploaded pharmaceutical applicant dossier (CTD 3.2.S.5).
    OTHER          — Any other supporting document.

    Regulatory note: source type must be preserved on every ExtractionResult so
    that applicant evidence (SCORE_REPORT), regulatory guidance (IPRP_GUIDANCE,
    PHARMACOPOEIA) and internal specifications (V2_MAPPING) are never conflated
    during retrieval or assessment.
    """
    IPRP_GUIDANCE = "iprp_guidance"
    PHARMACOPOEIA = "pharmacopoeia"
    V2_MAPPING    = "v2_mapping"
    SCORE_REPORT  = "score_report"
    APPLICANT_DOSSIER = "applicant_dossier"
    OTHER         = "other"


class DocumentRecord(BaseModel):
    """
    Metadata record for one ingested source document (Phase 2).

    doc_id is the SHA-256 hex digest of the raw file bytes, used for
    deduplication.  Re-uploading the same file returns the existing record.

    Fields:
      doc_id              — SHA-256(file bytes), hex string.
      filename            — Original filename as supplied by the uploader.
      source_type         — DocumentSourceType classification.
      page_count          — Total pages (PDF only; None for DOCX).
      section_count       — Number of ExtractionResult objects produced.
      ingested_at         — ISO 8601 UTC timestamp of ingestion.
      extraction_method   — Library used: "pypdf", "pdfplumber", "python-docx".
      ocr_used            — True if OCR was attempted (prototype: always False).
      warnings            — Non-fatal issues encountered during extraction.
    """
    doc_id: str
    filename: str
    source_type: DocumentSourceType
    page_count: Optional[int] = None
    section_count: int = 0
    ingested_at: str                    # ISO 8601 UTC
    extraction_method: str
    ocr_used: bool = False
    warnings: list[str] = []


class ExtractionResult(BaseModel):
    """
    One extracted section from an ingested document (Phase 2).

    Each result carries a provenance anchor (doc_id + page_or_line) so that
    every piece of extracted text can be traced back to its source location.

    Regulatory note: raw_text is verbatim extracted content only.  No
    inference, completion or fabrication is performed by the ingestor.

    Fields:
      doc_id                — FK → DocumentRecord.doc_id.
      section_id            — Identifier of the section, e.g. "S5-QAR-01",
                              "ph_eur_5_12_secondary_standards", "score_amlodipine_s5".
      section_title         — Human-readable section heading.
      page_or_line          — Location anchor, e.g. "p.18" (PDF) or "row 82" (DOCX table).
      raw_text              — Verbatim text as extracted from the document.
      source_type           — DocumentSourceType; copied from parent DocumentRecord.
      extraction_confidence — HIGH: clean digital text layer.
                              MEDIUM: partial extraction or heuristic section match.
                              LOW: empty or near-empty extraction; OCR may be needed.
      notes                 — Extractor annotations, e.g. "section boundary inferred".
    """
    doc_id: str
    section_id: str
    section_title: str
    page_or_line: Optional[str] = None
    raw_text: str
    source_type: DocumentSourceType
    extraction_confidence: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
    notes: list[str] = []


# ── Phase 9: IPRP-aligned structured assessment report ────────────────────────
# These models are ADDITIVE — they do not replace S5Claim, S5Finding or any
# existing model.  They are returned by the new POST /s5/assess endpoint and
# are never referenced by existing /s5/check or /s5/review endpoints.


class S5CriterionResult(BaseModel):
    """
    Structured assessment result for one IPRP S.5 criterion (Phase 9).

    criterion_id:
      S5-QAR-01 — Description and sources of reference standards or materials.
      S5-QAR-02 — Primary reference standard type and batch number.
      S5-QAR-03 — In-house primary RS characterisation, CoA and purity (where applicable).
      S5-QAR-04 — Secondary / working standard standardisation against primary.
      S5-AS-01  — Reference-standard sources and intended analytical uses.
      S5-AS-02  — Primary standard preparation, characterisation, purity and batch.
      S5-AS-03  — Secondary standard identification, assigned purity and batch.
      S5-AS-04  — Impurity standard characterisation and purity (where applicable).

    applicability values:
      APPLICABLE      — criterion clearly applies to this submission.
      NOT_APPLICABLE  — criterion does not apply (e.g. in-house criterion for a compendial RS).
      NOT_PROVIDED    — cannot determine; required fields are absent.
      UNCLEAR         — fields present but contradictory.

    evidence_verification_status values:
      SUPPORTED      — applicant-supplied values confirmed from an authoritative source.
      NOT_VERIFIED   — values present but not independently confirmed.
      NOT_APPLICABLE — criterion does not apply; no verification needed.
      MISSING        — required values absent; cannot assess.
    """
    criterion_id: str
    criterion_title: str
    applicability: str
    # Structured key-value pairs extracted from the S5Claim for this criterion.
    # None when applicability is NOT_APPLICABLE.
    extracted_info: Optional[dict] = None
    # List of doc_id + section_id references to supporting ingested documents.
    supporting_documents: list[str] = []
    # Applicable regulatory guidance references for this criterion.
    regulatory_guidance: str
    # Plain-English summary of the assessment outcome for this criterion.
    # None when applicability is NOT_APPLICABLE.
    assessment_finding: Optional[str] = None
    # List of fields / data items that are absent but required by IPRP.
    missing_info: list[str] = []
    # Verification status for the extracted values.
    evidence_verification_status: str = "NOT_VERIFIED"
    # Questions the assessor should raise with the applicant.
    assessor_questions: list[str] = []


class S5QAReviewSummary(BaseModel):
    """
    QA/Critic summary embedded in the S5AssessmentReport (Phase 9).

    Aggregates the qa_status and rule_references from the QA-stamped S5Finding
    alongside a consolidated list of evidence gaps across all criteria.

    This is a read-only summary — it does not replace the full S5Finding QA fields.
    """
    qa_status: Optional[Literal["PASS", "FLAG", "ESCALATE"]] = None
    rule_references: list[str] = []
    # Consolidated list of missing_info items from all criteria where
    # applicability == APPLICABLE.
    gaps: list[str] = []


class S5AssessmentReport(BaseModel):
    """
    Full IPRP-aligned structured assessment report for one S.5 submission (Phase 9).

    Contains exactly 8 S5CriterionResult objects in IPRP order:
      S5-QAR-01, S5-QAR-02, S5-QAR-03, S5-QAR-04,
      S5-AS-01,  S5-AS-02,  S5-AS-03,  S5-AS-04.

    This model is returned by POST /s5/assess alongside the S5Finding.
    It never replaces the S5Finding and does not modify verdict or qa_status.

    source_note is always populated and states whether evidence is real or mocked.
    """
    substance_name: str
    standard_claimed: str
    generated_at: str           # ISO 8601 UTC
    source_note: str
    criteria: list[S5CriterionResult]   # always exactly 8 items
    qa_review: S5QAReviewSummary


class S5AssessEndpointResponse(BaseModel):
    """
    Combined response from POST /s5/assess (Phase 9).

    s5_finding:        the existing S5Finding (QA-stamped via review_s5_finding).
    assessment_report: the new 8-criterion IPRP-aligned report.

    Returning both together means callers have the flat finding fields
    (verdict, evidence_sufficiency, completeness_flags) AND the full structured
    report without making two separate requests.
    """
    s5_finding: S5Finding
    assessment_report: S5AssessmentReport
