import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from adapters.m1_adapter import MockM1Adapter
from adapters.m4_adapter import LocalFileAuditAdapter, make_audit_record
from models import AssessorDecisionRequest, Finding, S5Claim, S5Finding, S5AssessEndpointResponse
from qa_critic import review_findings, review_s5_finding
from s5_standards import MockMonographRepository, check_s5_claim, build_assessment_report
from retrieval import query_ingested_documents


_KB_SOURCE_TYPES = ["iprp_guidance", "pharmacopoeia", "v2_mapping", "score_report"]

app = FastAPI(title="SAHPRA M5 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

# Adapter instances — swap these for real implementations once contracts are supplied
_m1 = MockM1Adapter()
_m4 = LocalFileAuditAdapter()
_monograph_repo = MockMonographRepository()

_FIXTURES = Path(__file__).parent / "mock_findings.json"


def _load_raw_findings() -> list[Finding]:
    data = json.loads(_FIXTURES.read_text(encoding="utf-8"))
    return [Finding(**item) for item in data["findings"]]


# ── Health ────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ── Findings ──────────────────────────────────────────────────────────

@app.get("/findings", response_model=list[Finding])
def get_findings():
    """Raw mock findings — no QA review applied."""
    return _load_raw_findings()


@app.get("/findings/reviewed", response_model=list[Finding])
def get_reviewed_findings():
    """
    Mock findings after QA/Critic review.
    In production this is replaced by findings returned from M1's /analyse endpoint.
    """
    findings = _m1.get_findings(dossier_id="mock")
    if isinstance(_m4, LocalFileAuditAdapter):
        decisions = _m4.latest_decisions()
        for finding in findings:
            if record := decisions.get(finding.finding_id):
                finding.assessor_decision = record.decision
                finding.disposition_note = record.disposition_note
                finding.decision_timestamp = datetime.fromisoformat(record.timestamp)
    return findings


@app.get("/findings/{finding_id}", response_model=Finding)
def get_finding(finding_id: str):
    findings = {f.finding_id: f for f in _load_raw_findings()}
    if finding_id not in findings:
        raise HTTPException(status_code=404, detail="Finding not found")
    return findings[finding_id]


# ── QA / Critic ───────────────────────────────────────────────────────

from pydantic import BaseModel  # noqa: E402 — kept at use site for clarity


class FindingsListRequest(BaseModel):
    findings: list[Finding]


class BatchS5CheckRequest(BaseModel):
    """
    Request body for POST /s5/check/batch.

    claims: 1–20 S5Claim objects to check in a single request.
    Each claim is processed independently against the monograph repository.
    Results are returned in the same order as the input claims.
    """
    claims: list[S5Claim]


@app.post("/qa/review", response_model=list[Finding])
def qa_review(body: FindingsListRequest):
    """
    Run the QA/Critic over a supplied list of findings.
    Returns the same findings with qa_status set on each.
    No findings are removed.
    """
    return review_findings(body.findings)


# ── S.5 Reference Standards ───────────────────────────────────────────

@app.post("/s5/check", response_model=S5Finding)
def s5_check(
    claim: S5Claim,
    retrieval_enabled: bool = Query(
        default=False,
        description=(
            "When True, perform live web retrieval via CrossRef and PubChem to "
            "populate provenance fields (source_url, retrieved_at, evidence_tier, "
            "content_verified, raw_excerpt). "
            "Defaults to False — no outbound network requests are made."
        ),
    ),
    ollama_enabled: bool = Query(
        default=False,
        description=(
            "When True, call the local Ollama LLM for AI reasoning commentary. "
            "Populates model_review on the returned S5Finding. "
            "Requires Ollama running at http://localhost:11434 with a supported model. "
            "Defaults to False — no Ollama call is made and model_review is null. "
            "AI output is never used to set verdict or evidence_sufficiency."
        ),
    ),
):
    """
    Check a sponsor's S.5 pharmacopoeial standard claim.
    Returns COMPLIANT, NON_COMPLIANT, or NEEDS_REVIEW — never an invented verdict.

    Optional query parameters:
      ?retrieval_enabled=true  — live CrossRef + PubChem lookup; populates provenance fields.
      ?ollama_enabled=true     — local Ollama LLM commentary; populates model_review.
    """
    return check_s5_claim(
        claim,
        _monograph_repo,
        retrieval_enabled=retrieval_enabled,
        ollama_enabled=ollama_enabled,
    )


@app.post("/s5/check/batch", response_model=list[S5Finding])
def s5_check_batch(
    body: BatchS5CheckRequest,
    retrieval_enabled: bool = Query(
        default=False,
        description=(
            "When True, perform live web retrieval via CrossRef and PubChem for each claim. "
            "Defaults to False — no outbound network requests are made."
        ),
    ),
    ollama_enabled: bool = Query(
        default=False,
        description=(
            "When True, call the local Ollama LLM for AI reasoning commentary on each claim. "
            "Requires Ollama running at http://localhost:11434 with a supported model. "
            "Defaults to False — no Ollama call is made and model_review is null on all results."
        ),
    ),
):
    """
    Check a batch of S.5 pharmacopoeial standard claims in a single request.

    Accepts 1–20 S5Claim objects and returns one S5Finding per claim, in the
    same order as the input.  Each claim is evaluated independently; there is
    no cross-claim interaction.

    Use POST /s5/check for a single claim with a richer docstring.
    Use POST /s5/review to apply QA rules (R11–R15) to the resulting findings.

    Returns HTTP 422 if the claims list is empty or contains more than 20 items.
    """
    if len(body.claims) == 0:
        raise HTTPException(status_code=422, detail="claims list must not be empty.")
    if len(body.claims) > 20:
        raise HTTPException(
            status_code=422,
            detail=f"claims list must not exceed 20 items (received {len(body.claims)}).",
        )
    return [
        check_s5_claim(
            claim,
            _monograph_repo,
            retrieval_enabled=retrieval_enabled,
            ollama_enabled=ollama_enabled,
        )
        for claim in body.claims
    ]


@app.post("/s5/review", response_model=S5Finding)
def s5_review(finding: S5Finding):
    """
    Run Phase 6 QA rules (R11–R15) over a completed S5Finding.

    Accepts an S5Finding (the output of POST /s5/check) and returns the same
    finding with qa_status and rule_references populated.

    Rules applied:
      R11 — evidence_sufficiency == INSUFFICIENT → FLAG
      R12 — verdict == NON_COMPLIANT → FLAG
      R13 — completeness_flags non-empty AND verdict == COMPLIANT → FLAG
      R14 — model_review present and non-empty → FLAG (AI issues require human adjudication)
      R15 — verdict == NEEDS_REVIEW → FLAG (pharmacopoeial manual check required)

    qa_status values:
      PASS — no rules fired; no immediate concerns identified.
      FLAG — one or more rules fired; human assessor review recommended.

    This endpoint does NOT modify verdict, evidence_sufficiency, completeness_flags,
    or any other assessment field.  It only sets qa_status and rule_references.

    The human assessor retains full decision-making authority.
    This output is not a regulatory determination.
    """
    return review_s5_finding(finding)


@app.post("/s5/assess", response_model=S5AssessEndpointResponse)
def s5_assess(
    claim: S5Claim,
    retrieval_enabled: bool = Query(
        default=False,
        description=(
            "When True, perform live web retrieval via CrossRef and PubChem. "
            "Defaults to False."
        ),
    ),
    ollama_enabled: bool = Query(
        default=False,
        description=(
            "When True, call the local Ollama LLM for AI reasoning commentary. "
            "Defaults to False."
        ),
    ),
):
    """
    Integrated IPRP S.5 assessment endpoint (Phase 9).

    Performs three operations in sequence and returns a combined response:

    1. check_s5_claim()     — pharmacopoeial edition/monograph lookup
                               → returns S5Finding (verdict, edition_current, etc.)
    2. review_s5_finding()  — QA rules R11–R15
                               → returns QA-stamped S5Finding (qa_status, rule_references)
    3. build_assessment_report() — IPRP 8-criterion structured report
                               → returns S5AssessmentReport

    Returns S5AssessEndpointResponse containing both the QA-stamped finding and the
    full assessment report.

    This endpoint does NOT replace /s5/check or /s5/review; they remain unchanged.

    The human assessor retains full decision-making authority.
    This output is not a regulatory determination.
    """
    # Step 1 — pharmacopoeial check
    finding: S5Finding = check_s5_claim(
        claim,
        _monograph_repo,
        retrieval_enabled=retrieval_enabled,
        ollama_enabled=ollama_enabled,
    )
    # Step 2 — QA critic auto-applied
    finding = review_s5_finding(finding)
    # Step 3 — retrieve KB hits for RAG evidence wiring
    _kb_hits = query_ingested_documents(
        standard=claim.standard,
        substance_name=claim.substance_name,
        source_types=_KB_SOURCE_TYPES,
    )
    # Step 4 — IPRP structured assessment report with RAG evidence
    report = build_assessment_report(claim, finding, kb_hits=_kb_hits)
    return S5AssessEndpointResponse(s5_finding=finding, assessment_report=report)


# ── Assessor decisions ────────────────────────────────────────────────

class DecisionResponse(BaseModel):
    finding_id: str
    decision: str
    timestamp: str
    audit_stub: bool
    audit_saved: bool
    message: str


@app.post("/decisions/{finding_id}", response_model=DecisionResponse)
def record_decision(finding_id: str, body: AssessorDecisionRequest):
    """
    Record an assessor decision for a finding.

    The decision is written to the local stub audit log (data/audit_log.jsonl).
    audit_stub=True and audit_saved reflects whether the write succeeded.
    This does NOT confirm that M4's real audit service has received the record.
    Replace _m4 with a real M4AuditAdapter once the contract is supplied.
    """
    if body.finding_id != finding_id:
        raise HTTPException(
            status_code=422,
            detail="finding_id in path and body must match",
        )

    record = make_audit_record(
        finding_id=finding_id,
        decision=body.decision,
        disposition_note=body.disposition_note,
    )
    saved = _m4.record_decision(record)

    return DecisionResponse(
        finding_id=finding_id,
        decision=body.decision,
        timestamp=record.timestamp,
        audit_stub=True,
        audit_saved=saved,
        message=(
            "Decision written to local stub audit log."
            if saved
            else "Decision processed but stub audit write failed."
        ),
    )


# ── M1 Human Gate callback ────────────────────────────────────────────

class HumanGateRequest(BaseModel):
    dossier_id: str
    findings: list[Finding]


class HumanGateResponse(BaseModel):
    dossier_id: str
    acknowledged: bool
    stub: bool
    message: str


@app.post("/m1/human-gate", response_model=HumanGateResponse)
def post_human_gate(body: HumanGateRequest):
    """
    Post QA-stamped findings and assessor decisions to M1's Human Gate.
    Currently a stub — replace _m1 with a real adapter once M1 supplies the contract.
    """
    ok = _m1.post_human_gate_result(
        dossier_id=body.dossier_id,
        findings=body.findings,
    )
    return HumanGateResponse(
        dossier_id=body.dossier_id,
        acknowledged=ok,
        stub=True,
        message="Stub: M1 Human Gate contract not yet supplied.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: Document Ingestion Endpoints
#
# Three new routes appended after the existing M1 human-gate endpoint.
# No existing route, model or logic has been modified.
#
# POST /documents/upload   — ingest one PDF or DOCX regulatory source document
# GET  /documents          — list all ingested documents
# GET  /documents/{doc_id}/extractions — return extracted sections for a doc
# ─────────────────────────────────────────────────────────────────────────────

from fastapi import UploadFile, File, Form
from ingestor import (
    ingest_document,
    list_documents as _list_docs,
    get_extractions as _get_extractions,
)
from models import DocumentSourceType, DocumentRecord, ExtractionResult


class DocumentUploadResponse(BaseModel):
    """Response returned after a successful document ingestion."""
    doc_id: str
    filename: str
    source_type: DocumentSourceType
    page_count: int | None
    section_count: int
    ingested_at: str
    extraction_method: str
    warnings: list[str]


@app.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    summary="Ingest a regulatory source document (PDF or DOCX)",
    tags=["Phase 2 - Document Ingestion"],
)
async def upload_document(
    file: UploadFile = File(...),
    source_type: str = Form(...),
):
    """
    Upload and ingest a regulatory source document.

    Accepted file types: .pdf, .docx (max 20 MB).

    source_type must be one of: iprp_guidance, pharmacopoeia,
    v2_mapping, score_report, other.

    Returns the content-addressable doc_id (SHA-256), the number of
    sections extracted, and any non-fatal warnings.

    HTTP 409 is returned when the same file (same content) has already
    been ingested.  The existing doc_id is included in the error detail.

    HTTP 422 is returned for validation failures (wrong type, too large,
    corrupt magic bytes, unknown source_type).

    Regulatory note: extracted text is verbatim.  No inference or
    fabrication is performed.  Source type is preserved on every
    ExtractionResult to prevent conflation of applicant evidence with
    regulatory guidance.
    """
    allowed_types = (*_KB_SOURCE_TYPES, DocumentSourceType.OTHER.value)
    if source_type not in allowed_types:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported source_type '{source_type}'. Valid values: {list(allowed_types)}",
        )
    st = DocumentSourceType(source_type)

    content = await file.read()
    filename = file.filename or "unknown"

    try:
        from ingestor import _DOC_STORE, compute_doc_id, validate_upload  # noqa
        validate_upload(filename, content)
        doc_id = compute_doc_id(content)
        if doc_id in _DOC_STORE:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Document already ingested",
                    "doc_id": doc_id,
                },
            )
        record, _ = ingest_document(content, filename, st)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return DocumentUploadResponse(
        doc_id=record.doc_id,
        filename=record.filename,
        source_type=record.source_type,
        page_count=record.page_count,
        section_count=record.section_count,
        ingested_at=record.ingested_at,
        extraction_method=record.extraction_method,
        warnings=record.warnings,
    )


@app.get(
    "/documents",
    response_model=list[DocumentRecord],
    summary="List all ingested documents",
    tags=["Phase 2 - Document Ingestion"],
)
def list_ingested_documents():
    """
    Return metadata for all documents that have been ingested in this session.

    The list is empty until at least one document has been uploaded via
    POST /documents/upload.  Results are stored in memory and are lost
    when the server restarts.
    """
    return _list_docs()


@app.get(
    "/documents/{doc_id}/extractions",
    response_model=list[ExtractionResult],
    summary="Return extracted sections for an ingested document",
    tags=["Phase 2 - Document Ingestion"],
)
def get_document_extractions(doc_id: str):
    """
    Return the list of ExtractionResult objects for the given doc_id.

    HTTP 404 is returned when the doc_id is not found.

    Each ExtractionResult carries:
      section_id    — structured identifier (e.g. "S5-QAR-01")
      page_or_line  — provenance anchor in the source document
      raw_text      — verbatim extracted text
      source_type   — IPRP_GUIDANCE | PHARMACOPOEIA | V2_MAPPING | SCORE_REPORT
      extraction_confidence — HIGH | MEDIUM | LOW
    """
    results = _get_extractions(doc_id)
    if results is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document with doc_id '{doc_id}' not found.",
        )
    return results
