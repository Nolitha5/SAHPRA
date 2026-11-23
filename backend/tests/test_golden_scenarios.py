"""
Golden-scenario validation tests.

Loads every golden-answer JSON file from tests/golden/ automatically.
For each file the test:
  1. Runs input.findings through the QA/Critic.
  2. Asserts every finding's qa_status matches expected_output.findings[*].qa_status.

Two parametrised suites cover all 13 scenarios individually so a failure
names the exact file that broke, without hiding other failures behind one
aggregate assert.

Naming convention: files must be named scenario_*.json and live in
tests/golden/ relative to the project root.
"""

import json
from pathlib import Path

import pytest

from models import Finding
from qa_critic import review_findings

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
# tests/ is at:  <project_root>/tests/golden/
# this file is:  <project_root>/backend/tests/test_golden_scenarios.py
# so project_root = Path(__file__).parent.parent.parent
GOLDEN_DIR = Path(__file__).parent.parent.parent / "tests" / "golden"

# ---------------------------------------------------------------------------
# Required _meta keys — every golden file must carry these
# ---------------------------------------------------------------------------
_REQUIRED_META_KEYS = ("scenario", "description", "version", "author")

# ---------------------------------------------------------------------------
# Valid qa_status values
# ---------------------------------------------------------------------------
_VALID_QA_STATUSES = {"PASS", "FLAG", "ESCALATE"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_scenario_files() -> list[Path]:
    """Return sorted list of all scenario_*.json paths in GOLDEN_DIR."""
    return sorted(GOLDEN_DIR.glob("scenario_*.json"))


def _scenario_names() -> list[str]:
    """File-name strings, used as pytest parametrize IDs."""
    return [p.name for p in _all_scenario_files()]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(path: Path) -> tuple[list[Finding], dict[str, str]]:
    """Run QA/Critic on a scenario; return (reviewed_findings, expected_map)."""
    data = _load(path)
    raw = [Finding(**f) for f in data["input"]["findings"]]
    reviewed = review_findings(raw)
    expected = {
        e["finding_id"]: e["qa_status"]
        for e in data["expected_output"]["findings"]
    }
    return reviewed, expected


# ---------------------------------------------------------------------------
# Suite 1 — file structure: all 13 files must have required keys
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename", _scenario_names())
def test_golden_file_structure(filename: str):
    """Every golden file must carry _meta, input.findings, and expected_output.findings."""
    data = _load(GOLDEN_DIR / filename)

    # Top-level keys
    assert "_meta" in data, f"{filename}: missing '_meta'"
    assert "input" in data, f"{filename}: missing 'input'"
    assert "expected_output" in data, f"{filename}: missing 'expected_output'"

    # _meta required sub-keys
    meta = data["_meta"]
    for key in _REQUIRED_META_KEYS:
        assert key in meta, f"{filename}: _meta missing '{key}'"

    # input.findings must be a non-empty list
    assert "findings" in data["input"], f"{filename}: input missing 'findings'"
    assert len(data["input"]["findings"]) > 0, f"{filename}: input.findings is empty"

    # expected_output.findings must be a list with valid qa_status values
    assert "findings" in data["expected_output"], (
        f"{filename}: expected_output missing 'findings'"
    )
    for entry in data["expected_output"]["findings"]:
        assert "finding_id" in entry, f"{filename}: expected entry missing 'finding_id'"
        assert "qa_status" in entry, f"{filename}: expected entry missing 'qa_status'"
        assert entry["qa_status"] in _VALID_QA_STATUSES, (
            f"{filename}: invalid qa_status {entry['qa_status']!r}"
        )


# ---------------------------------------------------------------------------
# Suite 2 — per-scenario status correctness: all 13 files
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("filename", _scenario_names())
def test_golden_scenario_qa_statuses(filename: str):
    """
    Run each golden scenario through the QA/Critic and assert every finding's
    qa_status matches the expected value declared in expected_output.findings.
    A failure message identifies the scenario file, finding ID, expected status
    and actual status.
    """
    reviewed, expected = _run(GOLDEN_DIR / filename)

    # Every expected finding_id must appear in the reviewed output
    reviewed_map = {f.finding_id: f.qa_status for f in reviewed}
    for fid in expected:
        assert fid in reviewed_map, (
            f"{filename}: finding '{fid}' present in expected_output but not in "
            f"QA/Critic output (got IDs: {list(reviewed_map)})"
        )

    # Every reviewed finding must match the expected status
    for finding in reviewed:
        fid = finding.finding_id
        assert fid in expected, (
            f"{filename}: finding '{fid}' returned by QA/Critic but not declared "
            f"in expected_output.findings"
        )
        assert finding.qa_status == expected[fid], (
            f"{filename} · {fid}: "
            f"expected qa_status={expected[fid]!r}, "
            f"got qa_status={finding.qa_status!r}"
        )

    # Count must match — no extra or missing findings
    assert len(reviewed) == len(expected), (
        f"{filename}: QA/Critic returned {len(reviewed)} findings, "
        f"expected_output declares {len(expected)}"
    )


# ---------------------------------------------------------------------------
# Suite 3 — aggregate sweep (kept for a quick single-assert CI check)
# ---------------------------------------------------------------------------

def test_all_golden_scenarios_pass_aggregate():
    """
    Single-assert sweep: all 13 scenarios correct.  Useful as a fast CI gate.
    For diagnostic detail on failure, run test_golden_scenario_qa_statuses instead.
    """
    failures: list[str] = []
    for path in _all_scenario_files():
        data = _load(path)
        if "findings" not in data.get("input", {}) or \
           "findings" not in data.get("expected_output", {}):
            continue
        reviewed, expected = _run(path)
        actual = {f.finding_id: f.qa_status for f in reviewed}
        if actual != expected:
            failures.append(
                f"{path.name}: expected {expected!r}, got {actual!r}"
            )
    assert not failures, "Golden scenario mismatches:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# Legacy named tests (kept for backward compatibility with any external runner)
# ---------------------------------------------------------------------------

def test_golden_pass_all_findings_pass():
    reviewed, expected = _run(GOLDEN_DIR / "scenario_pass.json")
    for finding in reviewed:
        assert finding.qa_status == expected[finding.finding_id]


def test_golden_pass_no_escalations():
    reviewed, _ = _run(GOLDEN_DIR / "scenario_pass.json")
    assert [f for f in reviewed if f.qa_status == "ESCALATE"] == []


def test_golden_identity_fail_finding_is_flagged():
    reviewed, expected = _run(GOLDEN_DIR / "scenario_identity_fail.json")
    for finding in reviewed:
        assert finding.qa_status == expected[finding.finding_id]


def test_golden_outdated_standard_finding_passes_qa():
    """
    The outdated-standard finding has a valid citation and consistent rationale.
    QA/Critic PASSes it -- the NON_COMPLIANT verdict comes from the S.5 agent.
    """
    reviewed, expected = _run(GOLDEN_DIR / "scenario_outdated_standard.json")
    for finding in reviewed:
        assert finding.qa_status == expected[finding.finding_id]
