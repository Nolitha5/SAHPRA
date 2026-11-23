"""
tests/test_phase6_api.py — Phase 6: API Endpoint Tests
=======================================================

Tests T-API-01 through T-API-10.

Coverage
--------
T-API-01  GET  /health                       → 200, {"status": "ok"}
T-API-02  POST /s5/check   full valid claim  → 200, verdict COMPLIANT, evidence_sufficiency SUPPORTED
T-API-03  POST /s5/check   claim with gaps   → 200, evidence_sufficiency != SUPPORTED
T-API-04  POST /s5/check   unknown substance → 200, evidence_sufficiency in {NOT_VERIFIED, INSUFFICIENT, PARTIAL}
T-API-05  POST /s5/check   missing required  → 422
T-API-06  POST /s5/review  COMPLIANT SUPPORTED finding  → 200, qa_status PASS, rule_references []
T-API-07  POST /s5/review  NON_COMPLIANT finding        → 200, qa_status FLAG, R12 in rule_references
T-API-08  POST /s5/review  NEEDS_REVIEW finding         → 200, qa_status FLAG, R15 in rule_references
T-API-09  POST /s5/check/batch  2-claim batch           → 200, list of 2 findings
T-API-10  POST /s5/check/batch  21-claim batch          → 422

This file must be run on the device (python -m pytest tests/test_phase6_api.py)
because main.py imports adapters.m1_adapter and adapters.m4_adapter which are
not part of the M5 staged files.

No confidential applicant data is used.
All test claims use the MockMonographRepository (no outbound network calls).
"""

import sys
import os
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

# A fully specified S5Claim that should produce COMPLIANT + SUPPORTED
_FULL_CLAIM = {
    "substance_name": "Aspirin",
    "standard": "USP",
    "edition_claimed": "USP 47",
    "submission_date": "2024-06-01",
    "standard_type": "compendial_primary",
    "lot_number": "LOT-ASP-01",
    "coa_submitted": True,
    "ir_spectra_submitted": True,
    "working_std_qualified_against_primary": True,
    "reference_standard_source_detail": "Purchased from USP catalogue",
}

# A claim that omits completeness sub-items (b/c/d) → flags → not SUPPORTED
_MINIMAL_CLAIM = {
    "substance_name": "Aspirin",
    "standard": "USP",
    "edition_claimed": "USP 47",
    "submission_date": "2024-06-01",
}

# A claim for a substance the mock repository has no record for → NEEDS_REVIEW
_UNKNOWN_CLAIM = {
    "substance_name": "UnknownSubstanceXYZ",
    "standard": "USP",
    "edition_claimed": "USP 47",
    "submission_date": "2024-06-01",
}

# A minimal valid S5Finding for /s5/review — COMPLIANT + SUPPORTED
_SUPPORTED_FINDING = {
    "substance_name": "Aspirin",
    "standard_claimed": "USP",
    "edition_claimed": "USP 47",
    "monograph_name": "Aspirin",
    "edition_current": "USP 47",
    "evidence": "Editions match.",
    "citation": "Aspirin, USP 47, p. 1251",
    "verdict": "COMPLIANT",
    "verdict_reason": "Claimed edition matches the current edition at submission date.",
    "source_note": "MOCK DATA — not from a real pharmacopoeia; for development only",
    "completeness_flags": [],
    "evidence_sufficiency": "SUPPORTED",
    "evidence_tier": "TIER_1_EXISTENCE_CONFIRMED",
    "content_verified": False,
    "qa_status": None,
    "rule_references": [],
    "model_review": None,
}

# A NON_COMPLIANT finding — R12 should fire
_NON_COMPLIANT_FINDING = {
    **_SUPPORTED_FINDING,
    "edition_current": "USP 48",
    "evidence": "Edition mismatch.",
    "verdict": "NON_COMPLIANT",
    "verdict_reason": "Claimed edition (USP 47) differs from current (USP 48).",
    "evidence_sufficiency": "PARTIAL",
    "citation": None,
}

# A NEEDS_REVIEW finding — R15 should fire
_NEEDS_REVIEW_FINDING = {
    **_SUPPORTED_FINDING,
    "edition_current": None,
    "evidence": "No monograph record found.",
    "verdict": "NEEDS_REVIEW",
    "verdict_reason": "No repository record available.",
    "evidence_sufficiency": "NOT_VERIFIED",
    "citation": None,
}


# ---------------------------------------------------------------------------
# T-API-01: GET /health
# ---------------------------------------------------------------------------

def test_tapi_01_health_returns_ok():
    """T-API-01: GET /health returns 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body.get("status") == "ok"


# ---------------------------------------------------------------------------
# T-API-02: POST /s5/check — full valid claim → COMPLIANT + SUPPORTED
# ---------------------------------------------------------------------------

def test_tapi_02_s5_check_full_claim_returns_supported():
    """T-API-02: fully specified claim → COMPLIANT + evidence_sufficiency SUPPORTED."""
    response = client.post("/s5/check", json=_FULL_CLAIM)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()
    assert body["verdict"] == "COMPLIANT", f"Expected COMPLIANT, got {body['verdict']!r}"
    assert body["evidence_sufficiency"] == "SUPPORTED", (
        f"Expected SUPPORTED, got {body['evidence_sufficiency']!r}"
    )
    # Phase 3/4 fields must be present in the response
    assert "evidence_tier" in body
    assert "content_verified" in body
    assert "completeness_flags" in body


# ---------------------------------------------------------------------------
# T-API-03: POST /s5/check — minimal claim (gaps) → evidence_sufficiency != SUPPORTED
# ---------------------------------------------------------------------------

def test_tapi_03_s5_check_minimal_claim_not_supported():
    """T-API-03: claim with missing sub-items → evidence_sufficiency is not SUPPORTED."""
    response = client.post("/s5/check", json=_MINIMAL_CLAIM)
    assert response.status_code == 200
    body = response.json()
    assert body["evidence_sufficiency"] != "SUPPORTED", (
        f"Did not expect SUPPORTED when completeness_flags={body.get('completeness_flags')!r}"
    )


# ---------------------------------------------------------------------------
# T-API-04: POST /s5/check — unknown substance → NOT_VERIFIED / INSUFFICIENT / PARTIAL
# ---------------------------------------------------------------------------

def test_tapi_04_s5_check_unknown_substance_not_supported():
    """T-API-04: unknown substance → evidence_sufficiency is not SUPPORTED."""
    response = client.post("/s5/check", json=_UNKNOWN_CLAIM)
    assert response.status_code == 200
    body = response.json()
    _allowed = {"NOT_VERIFIED", "INSUFFICIENT", "PARTIAL"}
    assert body["evidence_sufficiency"] in _allowed, (
        f"Expected one of {_allowed}, got {body['evidence_sufficiency']!r}"
    )


# ---------------------------------------------------------------------------
# T-API-05: POST /s5/check — missing required field → 422
# ---------------------------------------------------------------------------

def test_tapi_05_s5_check_missing_required_field_returns_422():
    """T-API-05: payload missing substance_name → 422 Unprocessable Entity."""
    invalid = {k: v for k, v in _FULL_CLAIM.items() if k != "substance_name"}
    response = client.post("/s5/check", json=invalid)
    assert response.status_code == 422, (
        f"Expected 422 for missing required field, got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# T-API-06: POST /s5/review — SUPPORTED finding → qa_status PASS
# ---------------------------------------------------------------------------

def test_tapi_06_s5_review_supported_finding_passes():
    """T-API-06: COMPLIANT + SUPPORTED finding → qa_status PASS, no rule_references."""
    response = client.post("/s5/review", json=_SUPPORTED_FINDING)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()
    assert body["qa_status"] == "PASS", f"Expected PASS, got {body['qa_status']!r}"
    assert body["rule_references"] == [], (
        f"Expected empty rule_references, got {body['rule_references']!r}"
    )


# ---------------------------------------------------------------------------
# T-API-07: POST /s5/review — NON_COMPLIANT finding → FLAG with R12
# ---------------------------------------------------------------------------

def test_tapi_07_s5_review_non_compliant_finding_flags_r12():
    """T-API-07: NON_COMPLIANT finding → qa_status FLAG, R12 in rule_references."""
    response = client.post("/s5/review", json=_NON_COMPLIANT_FINDING)
    assert response.status_code == 200
    body = response.json()
    assert body["qa_status"] == "FLAG", f"Expected FLAG, got {body['qa_status']!r}"
    refs = body["rule_references"]
    assert any("R12" in ref for ref in refs), (
        f"Expected R12 in rule_references, got {refs!r}"
    )


# ---------------------------------------------------------------------------
# T-API-08: POST /s5/review — NEEDS_REVIEW finding → FLAG with R15
# ---------------------------------------------------------------------------

def test_tapi_08_s5_review_needs_review_finding_flags_r15():
    """T-API-08: NEEDS_REVIEW finding → qa_status FLAG, R15 in rule_references."""
    response = client.post("/s5/review", json=_NEEDS_REVIEW_FINDING)
    assert response.status_code == 200
    body = response.json()
    assert body["qa_status"] == "FLAG", f"Expected FLAG, got {body['qa_status']!r}"
    refs = body["rule_references"]
    assert any("R15" in ref for ref in refs), (
        f"Expected R15 in rule_references, got {refs!r}"
    )


# ---------------------------------------------------------------------------
# T-API-09: POST /s5/check/batch — 2-claim batch → list of 2 findings
# ---------------------------------------------------------------------------

def test_tapi_09_s5_check_batch_two_claims():
    """T-API-09: batch of 2 claims returns 2 findings in the same order."""
    payload = {"claims": [_FULL_CLAIM, _MINIMAL_CLAIM]}
    response = client.post("/s5/check/batch", json=payload)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()
    assert isinstance(body, list), "Expected a list of findings"
    assert len(body) == 2, f"Expected 2 findings, got {len(body)}"
    # First finding should be for Aspirin
    assert body[0]["substance_name"] == "Aspirin"
    # Both findings must have evidence_sufficiency set
    assert body[0]["evidence_sufficiency"] is not None
    assert body[1]["evidence_sufficiency"] is not None


# ---------------------------------------------------------------------------
# T-API-10: POST /s5/check/batch — 21-claim batch → 422
# ---------------------------------------------------------------------------

def test_tapi_10_s5_check_batch_exceeds_limit_returns_422():
    """T-API-10: batch with 21 claims exceeds the 20-item limit → 422."""
    payload = {"claims": [_MINIMAL_CLAIM] * 21}
    response = client.post("/s5/check/batch", json=payload)
    assert response.status_code == 422, (
        f"Expected 422 for oversized batch, got {response.status_code}"
    )
