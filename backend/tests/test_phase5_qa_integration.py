"""
tests/test_phase5_qa_integration.py — Phase 5: QA Integration Tests
=====================================================================

Tests T-QI-01 through T-QI-10.

Coverage
--------
T-QI-01  COMPLIANT + SUPPORTED + no flags + no model_review  → qa_status PASS
T-QI-02  COMPLIANT + INSUFFICIENT + flags                     → qa_status FLAG  (R11)
T-QI-03  NON_COMPLIANT + PARTIAL + no flags                   → qa_status FLAG  (R12)
T-QI-04  COMPLIANT + PARTIAL + completeness flags             → qa_status FLAG  (R13)
T-QI-05  NEEDS_REVIEW + NOT_VERIFIED + no flags               → qa_status FLAG  (R15)
T-QI-06  NEEDS_REVIEW + INSUFFICIENT + flags                  → qa_status FLAG  (R11 + R15)
T-QI-07  COMPLIANT + SUPPORTED + model_review with issues     → qa_status FLAG  (R14)
T-QI-08  COMPLIANT + SUPPORTED + model_review empty lists     → qa_status PASS  (R14 not triggered)
T-QI-09  NON_COMPLIANT + PARTIAL + flags                      → qa_status FLAG  (R12 + R13)
T-QI-10  rule_references populated with correct R-code labels

No production code is modified.  No confidential applicant data is used.
All S5Finding objects are constructed directly — check_s5_claim() is not called.
"""

import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from models import S5Finding, ModelReview
from qa_critic import review_s5_finding


# ---------------------------------------------------------------------------
# Helper — build a minimal valid S5Finding with overridable fields
# ---------------------------------------------------------------------------

def _make_finding(**overrides) -> S5Finding:
    """
    Return an S5Finding with safe defaults.  Pass keyword overrides to test
    specific field combinations.
    """
    defaults = dict(
        substance_name="Aspirin",
        standard_claimed="USP",
        edition_claimed="USP 47",
        monograph_name="Aspirin",
        edition_current="USP 47",
        evidence="Edition matches.",
        citation="Aspirin, USP 47, p. 100",
        verdict="COMPLIANT",
        verdict_reason="Claimed edition matches the current edition.",
        source_note="MOCK DATA — not from a real pharmacopoeia; for development only",
        completeness_flags=[],
        evidence_sufficiency="SUPPORTED",
        evidence_tier="TIER_1_EXISTENCE_CONFIRMED",
        content_verified=False,
        qa_status=None,
        rule_references=[],
        model_review=None,
    )
    defaults.update(overrides)
    return S5Finding(**defaults)


# ---------------------------------------------------------------------------
# T-QI-01: clean SUPPORTED finding → PASS, no rule_references
# ---------------------------------------------------------------------------

def test_tqi_01_clean_supported_finding_passes():
    """T-QI-01: COMPLIANT + SUPPORTED + no flags + no model_review → PASS."""
    finding = _make_finding()
    result = review_s5_finding(finding)
    assert result.qa_status == "PASS", f"Expected PASS, got {result.qa_status!r}"
    assert result.rule_references == [], (
        f"Expected empty rule_references, got {result.rule_references!r}"
    )


# ---------------------------------------------------------------------------
# T-QI-02: INSUFFICIENT evidence → FLAG via R11
# ---------------------------------------------------------------------------

def test_tqi_02_insufficient_evidence_flags_r11():
    """T-QI-02: evidence_sufficiency == INSUFFICIENT triggers R11 → FLAG."""
    finding = _make_finding(
        verdict="NEEDS_REVIEW",
        evidence_sufficiency="INSUFFICIENT",
        completeness_flags=["sub-item (a): lot number not provided"],
        edition_current=None,
        citation=None,
    )
    result = review_s5_finding(finding)
    assert result.qa_status == "FLAG", f"Expected FLAG, got {result.qa_status!r}"
    assert any("R11" in ref for ref in result.rule_references), (
        f"Expected R11 in rule_references, got {result.rule_references!r}"
    )


# ---------------------------------------------------------------------------
# T-QI-03: NON_COMPLIANT verdict → FLAG via R12
# ---------------------------------------------------------------------------

def test_tqi_03_non_compliant_flags_r12():
    """T-QI-03: NON_COMPLIANT verdict triggers R12 → FLAG."""
    finding = _make_finding(
        verdict="NON_COMPLIANT",
        evidence_sufficiency="PARTIAL",
        edition_current="USP 48",
        verdict_reason="Claimed edition (USP 47) differs from current edition (USP 48).",
        completeness_flags=[],
    )
    result = review_s5_finding(finding)
    assert result.qa_status == "FLAG"
    assert any("R12" in ref for ref in result.rule_references), (
        f"Expected R12 in rule_references, got {result.rule_references!r}"
    )


# ---------------------------------------------------------------------------
# T-QI-04: COMPLIANT with completeness flags → FLAG via R13
# ---------------------------------------------------------------------------

def test_tqi_04_compliant_with_flags_triggers_r13():
    """T-QI-04: COMPLIANT verdict + non-empty completeness_flags → R13 → FLAG."""
    finding = _make_finding(
        verdict="COMPLIANT",
        evidence_sufficiency="PARTIAL",
        completeness_flags=["sub-item (b): CoA submission not stated"],
    )
    result = review_s5_finding(finding)
    assert result.qa_status == "FLAG"
    assert any("R13" in ref for ref in result.rule_references), (
        f"Expected R13 in rule_references, got {result.rule_references!r}"
    )


# ---------------------------------------------------------------------------
# T-QI-05: NEEDS_REVIEW verdict → FLAG via R15
# ---------------------------------------------------------------------------

def test_tqi_05_needs_review_flags_r15():
    """T-QI-05: NEEDS_REVIEW verdict triggers R15 → FLAG."""
    finding = _make_finding(
        verdict="NEEDS_REVIEW",
        evidence_sufficiency="NOT_VERIFIED",
        completeness_flags=[],
        edition_current=None,
        citation=None,
        verdict_reason="No monograph record available.",
    )
    result = review_s5_finding(finding)
    assert result.qa_status == "FLAG"
    assert any("R15" in ref for ref in result.rule_references), (
        f"Expected R15 in rule_references, got {result.rule_references!r}"
    )


# ---------------------------------------------------------------------------
# T-QI-06: NEEDS_REVIEW + INSUFFICIENT → FLAG via R11 + R15
# ---------------------------------------------------------------------------

def test_tqi_06_needs_review_insufficient_flags_r11_and_r15():
    """T-QI-06: NEEDS_REVIEW + INSUFFICIENT + flags → both R11 and R15 fire."""
    finding = _make_finding(
        verdict="NEEDS_REVIEW",
        evidence_sufficiency="INSUFFICIENT",
        completeness_flags=["sub-item (a): lot number not provided",
                            "sub-item (b): CoA submission not stated"],
        edition_current=None,
        citation=None,
        verdict_reason="No monograph record available.",
    )
    result = review_s5_finding(finding)
    assert result.qa_status == "FLAG"
    refs = result.rule_references
    assert any("R11" in ref for ref in refs), f"Expected R11 in {refs!r}"
    assert any("R15" in ref for ref in refs), f"Expected R15 in {refs!r}"


# ---------------------------------------------------------------------------
# T-QI-07: model_review with issues → FLAG via R14
# ---------------------------------------------------------------------------

def test_tqi_07_model_review_with_issues_flags_r14():
    """T-QI-07: model_review present with non-empty lists → R14 → FLAG."""
    mr = ModelReview(
        model_name="llama3.2",
        generated_at="2024-06-01T10:00:00Z",
        potential_issues=["Purity value appears inconsistent with stated lot."],
        missing_info=[],
        unsupported_conclusions=[],
        assessor_questions=[],
    )
    finding = _make_finding(model_review=mr)
    result = review_s5_finding(finding)
    assert result.qa_status == "FLAG"
    assert any("R14" in ref for ref in result.rule_references), (
        f"Expected R14 in rule_references, got {result.rule_references!r}"
    )


# ---------------------------------------------------------------------------
# T-QI-08: model_review present but all lists empty → PASS (R14 not triggered)
# ---------------------------------------------------------------------------

def test_tqi_08_model_review_empty_lists_does_not_flag():
    """T-QI-08: model_review with all empty lists → R14 NOT triggered → PASS."""
    mr = ModelReview(
        model_name="llama3.2",
        generated_at="2024-06-01T10:00:00Z",
        potential_issues=[],
        missing_info=[],
        unsupported_conclusions=[],
        assessor_questions=[],
    )
    finding = _make_finding(model_review=mr)
    result = review_s5_finding(finding)
    assert result.qa_status == "PASS", (
        f"Expected PASS with empty model_review lists, got {result.qa_status!r}"
    )
    assert not any("R14" in ref for ref in result.rule_references)


# ---------------------------------------------------------------------------
# T-QI-09: NON_COMPLIANT + completeness flags → FLAG via R12 + R13
# ---------------------------------------------------------------------------

def test_tqi_09_non_compliant_with_flags_fires_r12_only():
    """
    T-QI-09: NON_COMPLIANT verdict + completeness flags → R12 fires; R13 does NOT.

    R13 is scoped to verdict == COMPLIANT only (structural gaps on a passing edition).
    For NON_COMPLIANT, only R12 fires — the edition mismatch is the governing issue.
    """
    finding = _make_finding(
        verdict="NON_COMPLIANT",
        evidence_sufficiency="PARTIAL",
        completeness_flags=["sub-item (a): lot number not provided"],
        edition_current="USP 48",
        verdict_reason="Edition mismatch.",
    )
    result = review_s5_finding(finding)
    assert result.qa_status == "FLAG"
    refs = result.rule_references
    assert any("R12" in ref for ref in refs), f"Expected R12 in {refs!r}"
    assert not any("R13" in ref for ref in refs), (
        f"R13 must NOT fire for NON_COMPLIANT verdict, got {refs!r}"
    )


# ---------------------------------------------------------------------------
# T-QI-10: rule_references use the correct R-code label format
# ---------------------------------------------------------------------------

def test_tqi_10_rule_references_use_correct_label_format():
    """
    T-QI-10: rule_references entries must follow the 'R<n>:<code>' format
    defined in _CODE_TO_RULE_LABEL, not raw code strings.
    """
    # Trigger R11, R15 — NEEDS_REVIEW + INSUFFICIENT
    finding = _make_finding(
        verdict="NEEDS_REVIEW",
        evidence_sufficiency="INSUFFICIENT",
        completeness_flags=["sub-item (a): lot number not provided"],
        edition_current=None,
        citation=None,
        verdict_reason="No record available.",
    )
    result = review_s5_finding(finding)
    for ref in result.rule_references:
        # Each label must start with "R" followed by digits and a colon.
        assert ref.startswith("R") and ":" in ref, (
            f"rule_reference {ref!r} does not match expected 'R<n>:<code>' format"
        )
