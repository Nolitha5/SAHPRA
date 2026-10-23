"""
Golden-scenario validation tests.

Loads each golden-answer JSON file from tests/golden/, runs the input findings
through the QA/Critic, and asserts that every finding's qa_status matches the
expected value.  These tests give M4's evaluation harness a Python-based
reference check and confirm the golden files stay in sync with the QA rules.
"""

import json
from pathlib import Path

import pytest

from models import Finding
from qa_critic import review_findings

GOLDEN_DIR = Path(__file__).parent.parent.parent / "tests" / "golden"


def _load_scenario(name: str):
    path = GOLDEN_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def _run_scenario(scenario_name: str):
    data = _load_scenario(scenario_name)
    raw = [Finding(**f) for f in data["input"]["findings"]]
    reviewed = review_findings(raw)
    expected = {
        e["finding_id"]: e["qa_status"]
        for e in data["expected_output"]["findings"]
    }
    return reviewed, expected


# ── scenario: pass ────────────────────────────────────────────────────

def test_golden_pass_all_findings_pass():
    reviewed, expected = _run_scenario("scenario_pass.json")
    for finding in reviewed:
        assert finding.qa_status == expected[finding.finding_id], (
            f"{finding.finding_id}: expected {expected[finding.finding_id]!r}, "
            f"got {finding.qa_status!r}"
        )


def test_golden_pass_no_escalations():
    reviewed, _ = _run_scenario("scenario_pass.json")
    escalated = [f for f in reviewed if f.qa_status == "ESCALATE"]
    assert escalated == []


# ── scenario: identity_fail ───────────────────────────────────────────

def test_golden_identity_fail_finding_is_flagged():
    reviewed, expected = _run_scenario("scenario_identity_fail.json")
    for finding in reviewed:
        assert finding.qa_status == expected[finding.finding_id], (
            f"{finding.finding_id}: expected {expected[finding.finding_id]!r}, "
            f"got {finding.qa_status!r}"
        )


# ── scenario: outdated_standard ──────────────────────────────────────

def test_golden_outdated_standard_finding_passes_qa():
    """
    The outdated-standard finding has a valid citation and consistent rationale.
    QA/Critic should PASS it; the NON_COMPLIANT verdict comes from the S.5 agent.
    """
    reviewed, expected = _run_scenario("scenario_outdated_standard.json")
    for finding in reviewed:
        assert finding.qa_status == expected[finding.finding_id], (
            f"{finding.finding_id}: expected {expected[finding.finding_id]!r}, "
            f"got {finding.qa_status!r}"
        )


# ── golden files are valid JSON and have required keys ───────────────

@pytest.mark.parametrize("filename", [
    "scenario_pass.json",
    "scenario_identity_fail.json",
    "scenario_outdated_standard.json",
])
def test_golden_file_structure(filename: str):
    data = _load_scenario(filename)
    assert "_meta" in data
    assert "input" in data and "findings" in data["input"]
    assert "expected_output" in data and "findings" in data["expected_output"]
    for entry in data["expected_output"]["findings"]:
        assert "finding_id" in entry
        assert "qa_status" in entry
        assert entry["qa_status"] in ("PASS", "FLAG", "ESCALATE")
