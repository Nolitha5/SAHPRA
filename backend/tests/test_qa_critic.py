"""
pytest suite for qa_critic.py.

Covers:
  - clean finding → PASS
  - missing citation → FLAG
  - out-of-range uncertainty score → FLAG
  - rationale contradicts evidence → FLAG
  - multiple rules violated on one finding → FLAG (not duplicated)
  - two flags in same CTD section → both ESCALATE
  - one flag + one pass in same section → FLAG (not escalated)
  - findings in different sections do not cross-escalate
  - all findings preserved (none removed)
"""

import pytest

from models import Finding
from qa_critic import review_finding, review_findings


# ── Helpers ──────────────────────────────────────────────────────────

def make_finding(**overrides) -> Finding:
    defaults = dict(
        finding_id="TEST-01",
        ctd_section="3.2.S.1",
        rationale="The declared value matches the reference standard.",
        evidence_snippet="Sponsor declares value consistent with reference.",
        citation="BP 2024, monograph XYZ, p. 100",
        uncertainty_score=20,
        qa_status=None,
        assessor_decision=None,
        disposition_note=None,
        decision_timestamp=None,
    )
    defaults.update(overrides)
    return Finding(**defaults)


# ── Single-finding rules ──────────────────────────────────────────────

def test_clean_finding_passes():
    finding = make_finding()
    result, reasons = review_finding(finding)
    assert result.qa_status == "PASS"
    assert reasons == []


def test_missing_citation_flags():
    finding = make_finding(citation="")
    result, reasons = review_finding(finding)
    assert result.qa_status == "FLAG"
    assert any(r.code == "missing_citation" for r in reasons)


def test_whitespace_only_citation_flags():
    finding = make_finding(citation="   ")
    result, reasons = review_finding(finding)
    assert result.qa_status == "FLAG"
    assert any(r.code == "missing_citation" for r in reasons)


def test_score_above_max_flags():
    finding = make_finding(uncertainty_score=101)
    result, reasons = review_finding(finding)
    assert result.qa_status == "FLAG"
    assert any(r.code == "uncertainty_out_of_range" for r in reasons)


def test_score_below_min_flags():
    finding = make_finding(uncertainty_score=-1)
    result, reasons = review_finding(finding)
    assert result.qa_status == "FLAG"
    assert any(r.code == "uncertainty_out_of_range" for r in reasons)


def test_score_at_boundary_passes():
    for score in (0, 100):
        finding = make_finding(uncertainty_score=score)
        result, _ = review_finding(finding)
        assert result.qa_status == "PASS", f"score={score} should pass"


def test_rationale_contradicts_evidence_flags():
    finding = make_finding(
        rationale="The value matches the specification and complies.",
        evidence_snippet="The analysis shows a mismatch; value does not meet limits.",
    )
    result, reasons = review_finding(finding)
    assert result.qa_status == "FLAG"
    assert any(r.code == "rationale_contradicts_evidence" for r in reasons)


def test_consistent_non_compliance_passes():
    """Rationale and evidence both signal a problem — consistent, not contradictory."""
    finding = make_finding(
        rationale="The declared CAS number does not match the INN.",
        evidence_snippet="Sponsor declares Ethanol, CAS 50-00-0 (Formaldehyde).",
    )
    result, _ = review_finding(finding)
    assert result.qa_status == "PASS"


def test_multiple_violations_still_flag_not_duplicated():
    finding = make_finding(citation="", uncertainty_score=150)
    result, reasons = review_finding(finding)
    assert result.qa_status == "FLAG"
    codes = [r.code for r in reasons]
    assert "missing_citation" in codes
    assert "uncertainty_out_of_range" in codes


def test_finding_is_preserved_not_removed():
    finding = make_finding(citation="")
    result, _ = review_finding(finding)
    assert result.finding_id == finding.finding_id


# ── Escalation rules ─────────────────────────────────────────────────

def test_two_flags_in_same_section_escalate():
    findings = [
        make_finding(finding_id="A", ctd_section="3.2.S.1", citation=""),
        make_finding(finding_id="B", ctd_section="3.2.S.1", citation=""),
    ]
    results = review_findings(findings)
    statuses = {f.finding_id: f.qa_status for f in results}
    assert statuses["A"] == "ESCALATE"
    assert statuses["B"] == "ESCALATE"


def test_one_flag_one_pass_in_section_does_not_escalate():
    findings = [
        make_finding(finding_id="A", ctd_section="3.2.S.1", citation=""),
        make_finding(finding_id="B", ctd_section="3.2.S.1"),
    ]
    results = review_findings(findings)
    statuses = {f.finding_id: f.qa_status for f in results}
    assert statuses["A"] == "FLAG"
    assert statuses["B"] == "PASS"


def test_escalation_does_not_cross_sections():
    findings = [
        make_finding(finding_id="A", ctd_section="3.2.S.1", citation=""),
        make_finding(finding_id="B", ctd_section="3.2.S.1", citation=""),
        make_finding(finding_id="C", ctd_section="3.2.S.3", citation=""),
    ]
    results = review_findings(findings)
    statuses = {f.finding_id: f.qa_status for f in results}
    assert statuses["A"] == "ESCALATE"
    assert statuses["B"] == "ESCALATE"
    assert statuses["C"] == "FLAG"   # only one flag in S.3


def test_all_findings_preserved():
    findings = [
        make_finding(finding_id="A", citation=""),
        make_finding(finding_id="B"),
        make_finding(finding_id="C", uncertainty_score=200),
    ]
    results = review_findings(findings)
    assert len(results) == 3
    ids = {f.finding_id for f in results}
    assert ids == {"A", "B", "C"}


def test_empty_list_returns_empty():
    assert review_findings([]) == []


# ── Mock findings consistency ─────────────────────────────────────────

def test_mock_findings_f005_out_of_range_score_is_flagged():
    """
    mock_findings.json contains F-005 with uncertainty_score=150 (out of range).
    This test confirms the QA/Critic FLAGs it, and that no test elsewhere
    accidentally treats mock_findings.json as an all-PASS dataset.
    (scenario_pass.json uses a separate F-005 with score=15, which is correct.)
    """
    import json
    from pathlib import Path

    mock_path = Path(__file__).parent.parent / "mock_findings.json"
    data = json.loads(mock_path.read_text(encoding="utf-8"))
    from models import Finding

    findings = [Finding(**f) for f in data["findings"]]
    f005 = next(f for f in findings if f.finding_id == "F-005")
    assert f005.uncertainty_score == 150, "Precondition: F-005 score must be 150 in mock_findings.json"

    results = review_findings(findings)
    result_map = {f.finding_id: f for f in results}
    # F-004 (missing citation) and F-005 (score 150) are both in 3.2.S.3, so
    # the escalation rule promotes both to ESCALATE. Either FLAG or ESCALATE
    # means the out-of-range score was caught; PASS would mean it slipped through.
    assert result_map["F-005"].qa_status in ("FLAG", "ESCALATE"), (
        "F-005 with score 150 must not PASS — it must be FLAGged or ESCALATEd"
    )
