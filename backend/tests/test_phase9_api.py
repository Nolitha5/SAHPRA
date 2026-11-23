"""
Phase 2 — API integration tests (T-RPT-12 .. T-RPT-13).

Tests POST /s5/assess via FastAPI TestClient.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

COMPENDIAL_CLAIM = {
    "substance_name": "Amlodipine Besylate",
    "standard": "USP",
    "edition_claimed": "USP 47",
    "submission_date": "2024-03-01",
    "standard_type": "compendial",
    "lot_number": "R09060",
    "coa_submitted": True,
    "ir_spectra_submitted": True,
    "working_standard_lot": "WS-2024-01",
    "working_standard_source": "ABC Unit-7",
    "working_standard_assay": 100.4,
    "working_std_qualified_against_primary": True,
    "reference_standard_source_detail": "USP Reference Standards",
    "intended_use": ["identification", "assay"],
}


# ── T-RPT-12: POST /s5/assess returns 200 with correct top-level keys ─────────

def test_T_RPT_12_assess_endpoint_returns_200():
    resp = client.post("/s5/assess", json=COMPENDIAL_CLAIM)
    assert resp.status_code == 200
    body = resp.json()
    assert "s5_finding" in body
    assert "assessment_report" in body


# ── T-RPT-13: assessment_report contains exactly 8 criteria ──────────────────

def test_T_RPT_13_assess_report_has_8_criteria():
    resp = client.post("/s5/assess", json=COMPENDIAL_CLAIM)
    assert resp.status_code == 200
    report = resp.json()["assessment_report"]
    assert len(report["criteria"]) == 8
    ids = {c["criterion_id"] for c in report["criteria"]}
    expected = {
        "S5-QAR-01", "S5-QAR-02", "S5-QAR-03", "S5-QAR-04",
        "S5-AS-01",  "S5-AS-02",  "S5-AS-03",  "S5-AS-04",
    }
    assert ids == expected
