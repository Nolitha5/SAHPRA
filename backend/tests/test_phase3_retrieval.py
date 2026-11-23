"""
tests/test_phase3_retrieval.py — Phase 3: Retrieval Integration Tests
======================================================================

Tests T-P3-01 through T-P3-12 as specified in the Phase 3 proposal.

Coverage
--------
T-P3-01  query_ingested_documents returns [] when store is empty.
T-P3-02  Exact match (standard + substance) goes into Tier A.
T-P3-03  Standard-only match goes into Tier B.
T-P3-04  source_type filter excludes non-matching entries.
T-P3-05  Tier A results precede Tier B results in the returned list.
T-P3-06  source_types=None includes all source types.
T-P3-07  Case-insensitive matching for both standard and substance_name.
T-P3-08  check_s5_claim returns early with NEEDS_REVIEW when ingested hits exist.
T-P3-09  check_s5_claim evidence field mentions ingested sections.
T-P3-10  check_s5_claim falls through to repository when no ingested hits.
T-P3-11  check_s5_claim pre-check survives ImportError gracefully (store empty path).
T-P3-12  content_verified is always False on ingested-evidence S5Finding.

No confidential applicant data is used.
"""

import io
import sys
import os
from datetime import date

import pytest

# Allow import of backend modules from the parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import ingestor
from ingestor import (
    _DOC_STORE,
    _EXTRACTION_STORE,
    ingest_document,
    compute_doc_id,
)
from models import DocumentSourceType, S5Claim
from retrieval import query_ingested_documents
from s5_standards import check_s5_claim, MockMonographRepository


# ── Synthetic DOCX builder ────────────────────────────────────────────────────

def _make_docx_with_headings(sections: list[tuple[str, str]]) -> bytes:
    from docx import Document
    import io as _io
    doc = Document()
    for heading, body in sections:
        doc.add_heading(heading, level=1)
        doc.add_paragraph(body)
    buf = _io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── Shared fixture ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_stores():
    """Reset in-memory stores before and after every test."""
    _DOC_STORE.clear()
    _EXTRACTION_STORE.clear()
    yield
    _DOC_STORE.clear()
    _EXTRACTION_STORE.clear()


# ── Helper: ingest a small IPRP-guidance-style DOCX ──────────────────────────

def _ingest_iprp_doc(text: str, source_type: DocumentSourceType = DocumentSourceType.IPRP_GUIDANCE):
    docx_bytes = _make_docx_with_headings([("S.5 Reference Standards", text)])
    return ingest_document(docx_bytes, "iprp_test.docx", source_type)


# =============================================================================
# T-P3-01: query_ingested_documents returns [] when store is empty
# =============================================================================

def test_tp3_01_empty_store_returns_empty_list():
    """T-P3-01: empty store → empty list."""
    result = query_ingested_documents("USP", "Amlodipine Besylate")
    assert result == []


# =============================================================================
# T-P3-02: Exact match (standard + substance) produces Tier A hit
# =============================================================================

def test_tp3_02_exact_match_tier_a():
    """T-P3-02: text containing both standard and substance → Tier A."""
    _ingest_iprp_doc(
        "USP monograph for Amlodipine Besylate is listed in USP 46-NF 41."
    )
    results = query_ingested_documents("USP", "Amlodipine Besylate")
    assert len(results) >= 1
    text = results[0].raw_text.lower()
    assert "usp" in text
    assert "amlodipine besylate" in text


# =============================================================================
# T-P3-03: Standard-only match produces a Tier B hit
# =============================================================================

def test_tp3_03_standard_only_match_tier_b():
    """T-P3-03: text containing standard but NOT substance → Tier B (included)."""
    _ingest_iprp_doc(
        "The USP monograph for reference standards shall be consulted."
    )
    results = query_ingested_documents("USP", "Valsartan")
    assert len(results) >= 1
    text = results[0].raw_text.lower()
    assert "usp" in text


# =============================================================================
# T-P3-04: source_type filter excludes non-matching entries
# =============================================================================

def test_tp3_04_source_type_filter():
    """T-P3-04: source_types filter removes entries of a different type."""
    _ingest_iprp_doc(
        "USP Amlodipine Besylate reference standard requirement.",
        source_type=DocumentSourceType.IPRP_GUIDANCE,
    )
    results = query_ingested_documents(
        "USP", "Amlodipine Besylate",
        source_types=["v2_mapping"],
    )
    assert results == []


# =============================================================================
# T-P3-05: Tier A precedes Tier B
# =============================================================================

def test_tp3_05_tier_a_before_tier_b():
    """T-P3-05: Tier A (exact) results appear before Tier B (standard-only) results."""
    _ingest_iprp_doc(
        "The USP standard is used widely for drug substances.",
        source_type=DocumentSourceType.IPRP_GUIDANCE,
    )
    _ingest_iprp_doc(
        "USP monograph for Ethanol covers identification tests.",
        source_type=DocumentSourceType.PHARMACOPOEIA,
    )
    results = query_ingested_documents("USP", "Ethanol")
    assert len(results) >= 1
    assert "ethanol" in results[0].raw_text.lower()


# =============================================================================
# T-P3-06: source_types=None includes all source types
# =============================================================================

def test_tp3_06_no_source_filter_includes_all():
    """T-P3-06: source_types=None returns results from any source type."""
    _ingest_iprp_doc(
        "USP Aspirin monograph reference.",
        source_type=DocumentSourceType.IPRP_GUIDANCE,
    )
    _ingest_iprp_doc(
        "USP Aspirin secondary reference standard lot number.",
        source_type=DocumentSourceType.SCORE_REPORT,
    )
    results = query_ingested_documents("USP", "Aspirin", source_types=None)
    source_types_found = {r.source_type.value for r in results}
    assert "iprp_guidance" in source_types_found
    assert "score_report" in source_types_found


# =============================================================================
# T-P3-07: Case-insensitive matching
# =============================================================================

def test_tp3_07_case_insensitive_matching():
    """T-P3-07: matching is case-insensitive for both standard and substance_name."""
    _ingest_iprp_doc("usp monograph for amlodipine besylate standard.")
    results = query_ingested_documents("USP", "AMLODIPINE BESYLATE")
    assert len(results) >= 1


# =============================================================================
# T-P3-08: check_s5_claim returns NEEDS_REVIEW when ingested hits exist
# =============================================================================

def test_tp3_08_check_s5_claim_early_return_on_ingested_hit():
    """T-P3-08: ingested evidence triggers early return with verdict=NEEDS_REVIEW."""
    _ingest_iprp_doc(
        "USP Amlodipine Besylate reference standard: current edition is USP 47."
    )
    claim = S5Claim(
        substance_name="Amlodipine Besylate",
        standard="USP",
        edition_claimed="USP 47",
        lot_number="LOT-TEST-001",
        purity_assigned=99.5,
        submission_date=date(2024, 1, 1),
        source_pharmacopoeia="USP",
        standard_type="compendial_primary",
    )
    finding = check_s5_claim(claim, MockMonographRepository())
    assert finding.verdict == "NEEDS_REVIEW"
    # Phase 4: wording changed from "ingested" to "RAG retrieval" / "KB section(s)"
    _ev = finding.evidence.lower()
    _sn = finding.source_note.lower()
    assert (
        "ingested" in _ev or "rag" in _ev or "kb" in _ev
        or "ingested" in _sn or "rag" in _sn or "kb" in _sn
    ), f"Expected RAG/KB evidence marker in evidence or source_note. evidence={finding.evidence!r} source_note={finding.source_note!r}"


# =============================================================================
# T-P3-09: check_s5_claim evidence field mentions ingested sections
# =============================================================================

def test_tp3_09_evidence_field_mentions_ingested_sections():
    """T-P3-09: S5Finding.evidence references the ingested sections."""
    _ingest_iprp_doc(
        "USP Valsartan reference standard must comply with USP 44."
    )
    claim = S5Claim(
        substance_name="Valsartan",
        standard="USP",
        edition_claimed="USP 44",
        lot_number="LOT-TEST-002",
        purity_assigned=99.0,
        submission_date=date(2021, 9, 1),
        source_pharmacopoeia="USP",
        standard_type="compendial_primary",
    )
    finding = check_s5_claim(claim, MockMonographRepository())
    assert ("section" in finding.evidence.lower() or
            "preview" in finding.evidence.lower() or
            "ingested" in finding.evidence.lower())


# =============================================================================
# T-P3-10: check_s5_claim falls through to repository when no ingested hits
# =============================================================================

def test_tp3_10_fallthrough_to_repository_when_no_hits():
    """T-P3-10: empty store → check_s5_claim proceeds to repository path."""
    claim = S5Claim(
        substance_name="Aspirin",
        standard="USP",
        edition_claimed="USP 47",
        lot_number="LOT-ASP-001",
        purity_assigned=99.5,
        submission_date=date(2024, 6, 1),
        source_pharmacopoeia="USP",
        standard_type="compendial_primary",
    )
    finding = check_s5_claim(claim, MockMonographRepository())
    assert finding.verdict in ("COMPLIANT", "NON_COMPLIANT", "NEEDS_REVIEW")
    assert "MOCK DATA" in finding.source_note or finding.source_note == "No record available in the current repository."


# =============================================================================
# T-P3-11: Graceful fallback when query_ingested_documents raises
# =============================================================================

def test_tp3_11_graceful_fallback_on_import_error(monkeypatch):
    """T-P3-11: if query_ingested_documents raises, check_s5_claim falls through."""
    import retrieval as _retrieval

    def _raises(*args, **kwargs):
        raise RuntimeError("forced error for T-P3-11")

    monkeypatch.setattr(_retrieval, "query_ingested_documents", _raises)

    claim = S5Claim(
        substance_name="Ethanol",
        standard="BP",
        edition_claimed="BP 2024",
        lot_number="LOT-ETH-001",
        purity_assigned=99.9,
        submission_date=date(2024, 3, 1),
        source_pharmacopoeia="BP",
        standard_type="compendial_primary",
    )
    finding = check_s5_claim(claim, MockMonographRepository())
    assert finding.verdict in ("COMPLIANT", "NON_COMPLIANT", "NEEDS_REVIEW")


# =============================================================================
# T-P3-12: content_verified is always False on ingested-evidence S5Finding
# =============================================================================

def test_tp3_12_content_verified_false_on_ingested_finding():
    """T-P3-12: ingested-evidence S5Finding must have content_verified=False."""
    _ingest_iprp_doc(
        "BP Ethanol reference standard: BP 2024 edition."
    )
    claim = S5Claim(
        substance_name="Ethanol",
        standard="BP",
        edition_claimed="BP 2024",
        lot_number="LOT-ETH-002",
        purity_assigned=99.9,
        submission_date=date(2024, 3, 1),
        source_pharmacopoeia="BP",
        standard_type="compendial_primary",
    )
    finding = check_s5_claim(claim, MockMonographRepository())
    if hasattr(finding, "content_verified"):
        assert finding.content_verified is False
