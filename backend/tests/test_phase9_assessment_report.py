"""
Phase 2 — Assessment Report unit tests (T-RPT-01 .. T-RPT-11).

Tests build_assessment_report() in isolation using synthetic S5Claim and
S5Finding objects.  No live backend, no real applicant data.
"""
import pytest
from datetime import datetime, timezone

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    S5Claim,
    S5Finding,
    S5AssessmentReport,
    S5CriterionResult,
)
from s5_standards import build_assessment_report


# ── helpers ──────────────────────────────────────────────────────────────────

def _base_claim(**overrides) -> S5Claim:
    defaults = dict(
        substance_name="TestSubstance",
        standard="USP",
        edition_claimed="USP 47",
        submission_date="2024-01-01",
        standard_type="compendial",
        lot_number="LOT-001",
        coa_submitted=True,
        ir_spectra_submitted=True,
        working_standard_lot="WS-001",
        working_standard_source="ABC Lab",
        working_standard_assay=99.8,
        working_std_qualified_against_primary=True,
        reference_standard_source_detail="USP Reference Standards",
        intended_use=["identification", "assay"],   # list[str] per model
    )
    defaults.update(overrides)
    return S5Claim(**defaults)


def _base_finding(**overrides) -> S5Finding:
    defaults = dict(
        substance_name="TestSubstance",        # required
        standard_claimed="USP 47",             # required
        edition_claimed="USP 47",              # required
        evidence="Edition verified",           # required (not evidence_snippet)
        verdict="COMPLIANT",
        verdict_reason="Edition matches",
        source_note="Test source",
        qa_status="PASS",
        rule_references=["IPRP-S5-QAR-01"],
        completeness_flags=[],
    )
    defaults.update(overrides)
    return S5Finding(**defaults)


# ── T-RPT-01: return type ─────────────────────────────────────────────────────

def test_T_RPT_01_returns_assessment_report():
    claim = _base_claim()
    finding = _base_finding()
    report = build_assessment_report(claim, finding)
    assert isinstance(report, S5AssessmentReport)


# ── T-RPT-02: exactly 8 criteria ─────────────────────────────────────────────

def test_T_RPT_02_eight_criteria():
    report = build_assessment_report(_base_claim(), _base_finding())
    assert len(report.criteria) == 8


# ── T-RPT-03: criterion IDs match the IPRP spec ───────────────────────────────

def test_T_RPT_03_criterion_ids():
    expected = {
        "S5-QAR-01", "S5-QAR-02", "S5-QAR-03", "S5-QAR-04",
        "S5-AS-01",  "S5-AS-02",  "S5-AS-03",  "S5-AS-04",
    }
    report = build_assessment_report(_base_claim(), _base_finding())
    ids = {c.criterion_id for c in report.criteria}
    assert ids == expected


# ── T-RPT-04: substance_name and standard_claimed propagated correctly ─────────

def test_T_RPT_04_substance_and_standard():
    claim = _base_claim(substance_name="Amlodipine Besylate", standard="BP",
                        edition_claimed="BP 2024")
    report = build_assessment_report(claim, _base_finding())
    assert report.substance_name == "Amlodipine Besylate"
    assert "BP" in report.standard_claimed


# ── T-RPT-05: generated_at is a parseable ISO timestamp ───────────────────────

def test_T_RPT_05_generated_at_is_iso():
    report = build_assessment_report(_base_claim(), _base_finding())
    # Should not raise
    dt = datetime.fromisoformat(report.generated_at.replace("Z", "+00:00"))
    assert dt is not None


# ── T-RPT-06: compendial claim → S5-QAR-03 is NOT_APPLICABLE ─────────────────

def test_T_RPT_06_compendial_qar03_not_applicable():
    claim = _base_claim(standard_type="compendial")
    report = build_assessment_report(claim, _base_finding())
    qar03 = next(c for c in report.criteria if c.criterion_id == "S5-QAR-03")
    assert qar03.applicability == "NOT_APPLICABLE"


# ── T-RPT-07: in-house claim → S5-QAR-03 is APPLICABLE ───────────────────────

def test_T_RPT_07_inhouse_qar03_applicable():
    claim = _base_claim(
        standard_type="in-house",
        inhouse_characterisation_methods=["IR", "NMR", "HPLC"],
        inhouse_purity_assigned=True,
        inhouse_coa_submitted=True,
    )
    report = build_assessment_report(claim, _base_finding())
    qar03 = next(c for c in report.criteria if c.criterion_id == "S5-QAR-03")
    assert qar03.applicability == "APPLICABLE"


# ── T-RPT-08: missing working_standard_assay → gap flagged in S5-QAR-04 ──────

def test_T_RPT_08_missing_working_standard_assay():
    claim = _base_claim(working_standard_assay=None)
    report = build_assessment_report(claim, _base_finding())
    qar04 = next(c for c in report.criteria if c.criterion_id == "S5-QAR-04")
    assert len(qar04.missing_info) > 0


# ── T-RPT-09: impurity_standards=None → S5-AS-04 is NOT_PROVIDED ─────────────

def test_T_RPT_09_no_impurity_standards():
    claim = _base_claim(impurity_standards=None)
    report = build_assessment_report(claim, _base_finding())
    as04 = next(c for c in report.criteria if c.criterion_id == "S5-AS-04")
    assert as04.applicability == "NOT_PROVIDED"


# ── T-RPT-10: impurity_standards=[] → S5-AS-04 APPLICABLE with missing gap ───

def test_T_RPT_10_empty_impurity_standards():
    claim = _base_claim(impurity_standards=[])
    report = build_assessment_report(claim, _base_finding())
    as04 = next(c for c in report.criteria if c.criterion_id == "S5-AS-04")
    assert as04.applicability == "APPLICABLE"
    assert len(as04.missing_info) > 0


# ── T-RPT-11: qa_review mirrors finding qa_status ────────────────────────────

def test_T_RPT_11_qa_review_mirrors_finding():
    finding = _base_finding(qa_status="FLAG")
    report = build_assessment_report(_base_claim(), finding)
    assert report.qa_review.qa_status == "FLAG"
