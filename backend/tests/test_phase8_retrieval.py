"""
tests/test_phase8_retrieval.py — Phase 8: Retrieval Integration Tests
======================================================================

Tests T-RET-01 through T-RET-10.

Coverage
--------
T-RET-01  Empty store → query_ingested_documents returns []
T-RET-02  One matching doc → 1 result with doc_id, raw_text, source_type
T-RET-03  Non-matching substance_name → []
T-RET-04  Non-matching standard → []
T-RET-05  Two docs with same standard/substance → both returned
T-RET-06  source_types filter matching → only matching results
T-RET-07  source_types filter non-matching → []
T-RET-08  Case-insensitive match on substance_name and standard
T-RET-09  Multiple standards in store → query isolates correct standard
T-RET-10  Each result has required fields: doc_id, raw_text, source_type

Must be run on the device (python -m pytest tests/test_phase8_retrieval.py)
because main.py imports adapters.m1_adapter and adapters.m4_adapter.

No confidential applicant data is used.
"""

import io
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from main import app
from ingestor import _DOC_STORE, _EXTRACTION_STORE
from retrieval import query_ingested_documents

client = TestClient(app)

# ---------------------------------------------------------------------------
# Synthetic DOCX builder
# ---------------------------------------------------------------------------

def _make_docx(sections: list[tuple[str, str]]) -> bytes:
    """Build a minimal in-memory DOCX from (heading, body) pairs."""
    from docx import Document
    doc = Document()
    for heading, body in sections:
        doc.add_heading(heading, level=1)
        doc.add_paragraph(body)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Autouse fixture — clear stores before and after every test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_stores():
    _DOC_STORE.clear()
    _EXTRACTION_STORE.clear()
    yield
    _DOC_STORE.clear()
    _EXTRACTION_STORE.clear()


# ---------------------------------------------------------------------------
# Upload helper
# ---------------------------------------------------------------------------

def _upload(heading: str, body: str, source_type: str = "iprp_guidance",
            filename: str = "test.docx") -> str:
    """Upload a single-section DOCX and return the doc_id."""
    docx_bytes = _make_docx([(heading, body)])
    resp = client.post(
        "/documents/upload",
        files={"file": (filename,
                        docx_bytes,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"source_type": source_type},
    )
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()["doc_id"]


# ---------------------------------------------------------------------------
# T-RET-01: Empty store → []
# ---------------------------------------------------------------------------

def test_tret_01_empty_store_returns_empty_list():
    """T-RET-01: no documents ingested → query_ingested_documents returns []."""
    result = query_ingested_documents("USP", "Aspirin")
    assert result == [], f"Expected [], got {result!r}"


# ---------------------------------------------------------------------------
# T-RET-02: One matching doc → 1 result with key fields
# ---------------------------------------------------------------------------

def test_tret_02_single_match_returns_one_result():
    """T-RET-02: one uploaded doc whose text contains standard + substance → 1 result."""
    _upload(
        heading="S.5 Reference Standards",
        body="USP Aspirin reference standard — lot R09060, USP 47.",
        source_type="iprp_guidance",
        filename="asp_usp.docx",
    )
    results = query_ingested_documents("USP", "Aspirin")
    assert len(results) == 1, f"Expected 1 result, got {len(results)}"
    r = results[0]
    # Must have raw_text, source_type and be linked to a doc_id via the store
    assert hasattr(r, "raw_text"), "ExtractionResult missing raw_text"
    assert r.raw_text, "raw_text must not be empty"
    assert hasattr(r, "source_type"), "ExtractionResult missing source_type"


# ---------------------------------------------------------------------------
# T-RET-03: Non-matching substance_name → []
# ---------------------------------------------------------------------------

def test_tret_03_standard_only_match_returns_tier_b_result():
    """
    T-RET-03: doc contains standard (USP) but NOT the queried substance (Paracetamol).

    query_ingested_documents implements a three-tier ranking:
      Tier A — standard + substance both match
      Tier B — standard match only
      Tier C — source_type match only (when source_types filter is set)

    A standard-only match is a Tier B result and IS returned (not filtered out).
    This test verifies that:
    1. At least one result is returned (Tier B match on standard).
    2. The queried substance does NOT appear in any result's raw_text,
       confirming it is a standard-only (not full) match.
    """
    _upload(
        heading="S.5 Reference Standards",
        body="USP Ibuprofen reference standard — lot R12345, USP 47.",
        source_type="iprp_guidance",
        filename="ibu_usp.docx",
    )
    results = query_ingested_documents("USP", "Paracetamol")
    # Tier B: standard matched → at least 1 result returned
    assert len(results) >= 1, (
        "Expected at least 1 Tier B result (standard-only match)"
    )
    # Substance NOT in any result's raw_text (confirms it is a standard-only match)
    for r in results:
        assert "paracetamol" not in r.raw_text.lower(), (
            f"Did not expect 'paracetamol' in Tier B raw_text: {r.raw_text!r}"
        )


# ---------------------------------------------------------------------------
# T-RET-04: Non-matching standard → []
# ---------------------------------------------------------------------------

def test_tret_04_non_matching_standard_returns_empty():
    """T-RET-04: uploaded doc contains substance but NOT the queried standard → []."""
    _upload(
        heading="S.5 Reference Standards",
        body="BP Aspirin reference standard — BP 2024.",
        source_type="pharmacopoeia",
        filename="asp_bp.docx",
    )
    # Query for USP when doc only mentions BP
    results = query_ingested_documents("USP", "Aspirin")
    assert results == [], (
        f"Expected [] for non-matching standard, got {len(results)} result(s)"
    )


# ---------------------------------------------------------------------------
# T-RET-05: Two docs matching same standard/substance → both returned
# ---------------------------------------------------------------------------

def test_tret_05_two_matching_docs_both_returned():
    """T-RET-05: two docs that both mention standard + substance → 2 results."""
    _upload(
        heading="S.5 — Document A",
        body="USP Aspirin reference standard — lot A001, USP 47.",
        source_type="iprp_guidance",
        filename="asp_a.docx",
    )
    _upload(
        heading="S.5 — Document B",
        body="Aspirin monograph. USP 47 edition confirms identity.",
        source_type="pharmacopoeia",
        filename="asp_b.docx",
    )
    results = query_ingested_documents("USP", "Aspirin")
    assert len(results) == 2, f"Expected 2 results, got {len(results)}"


# ---------------------------------------------------------------------------
# T-RET-06: source_types filter — matching → only that source_type returned
# ---------------------------------------------------------------------------

def test_tret_06_source_types_filter_matching():
    """T-RET-06: source_types=['pharmacopoeia'] returns only pharmacopoeia extractions."""
    _upload(
        heading="Guidance",
        body="USP Aspirin reference standard per IPRP guidance.",
        source_type="iprp_guidance",
        filename="asp_iprp.docx",
    )
    _upload(
        heading="Monograph",
        body="USP Aspirin monograph — official pharmacopoeia entry.",
        source_type="pharmacopoeia",
        filename="asp_ph.docx",
    )
    results = query_ingested_documents("USP", "Aspirin", source_types=["pharmacopoeia"])
    assert len(results) >= 1, "Expected at least 1 pharmacopoeia result"
    for r in results:
        assert r.source_type.value == "pharmacopoeia", (
            f"Expected source_type=pharmacopoeia, got {r.source_type.value!r}"
        )


# ---------------------------------------------------------------------------
# T-RET-07: source_types filter — non-matching → []
# ---------------------------------------------------------------------------

def test_tret_07_source_types_filter_non_matching_returns_empty():
    """T-RET-07: filtering by a source_type not present in store → []."""
    _upload(
        heading="S.5 Reference Standards",
        body="USP Aspirin reference standard — lot R09060, USP 47.",
        source_type="iprp_guidance",
        filename="asp_iprp2.docx",
    )
    # Only iprp_guidance was uploaded; filter for score_report should return []
    results = query_ingested_documents("USP", "Aspirin", source_types=["score_report"])
    assert results == [], (
        f"Expected [] when filtering by absent source_type, got {len(results)} result(s)"
    )


# ---------------------------------------------------------------------------
# T-RET-08: Case-insensitive matching
# ---------------------------------------------------------------------------

def test_tret_08_case_insensitive_matching():
    """T-RET-08: query is case-insensitive for both standard and substance_name."""
    _upload(
        heading="S.5 Reference Standards",
        body="USP Aspirin reference standard — lot R09060, USP 47.",
        source_type="iprp_guidance",
        filename="asp_case.docx",
    )
    # Query with different case — should still match
    results_upper = query_ingested_documents("USP", "ASPIRIN")
    results_lower = query_ingested_documents("usp", "aspirin")
    results_mixed = query_ingested_documents("Usp", "Aspirin")

    assert len(results_upper) >= 1, "UPPERCASE query should match"
    assert len(results_lower) >= 1, "lowercase query should match"
    assert len(results_mixed) >= 1, "Mixed case query should match"


# ---------------------------------------------------------------------------
# T-RET-09: Multiple standards in store → correct standard isolated
# ---------------------------------------------------------------------------

def test_tret_09_multiple_standards_isolated():
    """T-RET-09: store has docs for USP and BP; query for USP returns only USP docs."""
    _upload(
        heading="USP Section",
        body="USP Aspirin reference standard. USP 47 edition.",
        source_type="iprp_guidance",
        filename="asp_usp2.docx",
    )
    _upload(
        heading="BP Section",
        body="BP Aspirin reference standard. BP 2024 edition.",
        source_type="pharmacopoeia",
        filename="asp_bp2.docx",
    )
    usp_results = query_ingested_documents("USP", "Aspirin")
    bp_results = query_ingested_documents("BP", "Aspirin")

    # USP query should return at least the USP doc
    assert len(usp_results) >= 1, "Expected at least 1 USP result"
    for r in usp_results:
        assert "usp" in r.raw_text.lower(), (
            f"USP result raw_text does not contain 'usp': {r.raw_text!r}"
        )

    # BP query should return at least the BP doc
    assert len(bp_results) >= 1, "Expected at least 1 BP result"
    for r in bp_results:
        assert "bp" in r.raw_text.lower(), (
            f"BP result raw_text does not contain 'bp': {r.raw_text!r}"
        )


# ---------------------------------------------------------------------------
# T-RET-10: Each result has required fields
# ---------------------------------------------------------------------------

def test_tret_10_results_have_required_fields():
    """T-RET-10: every ExtractionResult has doc_id, raw_text, source_type."""
    _upload(
        heading="S.5 Reference Standards",
        body="USP Aspirin reference standard — lot R09060, USP 47.",
        source_type="v2_mapping",
        filename="asp_v2.docx",
    )
    results = query_ingested_documents("USP", "Aspirin")
    assert len(results) >= 1, "Expected at least 1 result"
    for r in results:
        assert hasattr(r, "doc_id"), f"ExtractionResult missing doc_id: {r!r}"
        assert isinstance(r.doc_id, str) and len(r.doc_id) == 64, (
            f"doc_id should be 64-char SHA-256 hex, got {r.doc_id!r}"
        )
        assert hasattr(r, "raw_text"), f"ExtractionResult missing raw_text: {r!r}"
        assert r.raw_text, "raw_text must not be empty"
        assert hasattr(r, "source_type"), f"ExtractionResult missing source_type: {r!r}"
