"""
Tests for Finding.rule_references population by the QA/Critic.

Verifies that:
  - Each rule (R1–R7) sets exactly the right label in rule_references.
  - A PASS finding has an empty rule_references list.
  - Multiple rules firing on the same finding all appear.
  - Section-escalation promotion (FLAG → ESCALATE) preserves rule_references.
  - review_finding() (single-finding helper) also sets rule_references.
"""

import pytest

from models import Finding
from qa_critic import review_finding, review_findings

# ---------------------------------------------------------------------------
# Shared factory
# ---------------------------------------------------------------------------

def _make(
    finding_id: str = "F-TEST",
    ctd_section: str = "3.2.S.1",
    rationale: str = "The substance meets the specification.",
    evidence: str = "Results are within the acceptable limits.",
    citation: str = "BP 2024, p. 100",
    uncertainty_score: int = 10,
) -> Finding:
    return Finding(
        finding_id=finding_id,
        ctd_section=ctd_section,
        rationale=rationale,
        evidence_snippet=evidence,
        citation=citation,
        uncertainty_score=uncertainty_score,
    )


def _s5(
    finding_id: str = "F-S5",
    rationale: str = "USPRS lot R09060 used. CoA submitted. Overlaid IR spectra submitted. Working standard qualified against primary standard. Source: USP.",
    evidence: str = "Reference standard lot R09060 confirmed compliant. IR spectra overlaid.",
    **kwargs,
) -> Finding:
    return _make(
        finding_id=finding_id,
        ctd_section="3.2.S.5",
        rationale=rationale,
        evidence=evidence,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# PASS — no rules fired
# ---------------------------------------------------------------------------

def test_pass_finding_has_empty_rule_references():
    f, reasons = review_finding(_make())
    assert f.rule_references == []
    assert f.qa_status == "PASS"


def test_s5_pass_finding_has_empty_rule_references():
    f, reasons = review_finding(_s5())
    assert f.rule_references == []
    assert f.qa_status == "PASS"


# ---------------------------------------------------------------------------
# R1 — missing citation
# ---------------------------------------------------------------------------

def test_r1_sets_rule_reference():
    f, _ = review_finding(_make(citation=""))
    assert "R1:missing_citation" in f.rule_references


def test_r1_whitespace_citation_sets_rule_reference():
    f, _ = review_finding(_make(citation="   "))
    assert "R1:missing_citation" in f.rule_references


# ---------------------------------------------------------------------------
# R2 — uncertainty score out of range
# ---------------------------------------------------------------------------

def test_r2_above_max_sets_rule_reference():
    f, _ = review_finding(_make(uncertainty_score=101))
    assert "R2:uncertainty_out_of_range" in f.rule_references


def test_r2_below_min_sets_rule_reference():
    f, _ = review_finding(_make(uncertainty_score=-1))
    assert "R2:uncertainty_out_of_range" in f.rule_references


def test_r2_boundary_zero_no_rule_reference():
    f, _ = review_finding(_make(uncertainty_score=0))
    assert "R2:uncertainty_out_of_range" not in f.rule_references


def test_r2_boundary_hundred_no_rule_reference():
    f, _ = review_finding(_make(uncertainty_score=100))
    assert "R2:uncertainty_out_of_range" not in f.rule_references


# ---------------------------------------------------------------------------
# R3 — rationale contradicts evidence
# ---------------------------------------------------------------------------

def test_r3_contradiction_sets_rule_reference():
    f, _ = review_finding(_make(
        rationale="The substance meets the specification.",
        evidence="Results are outdated and fail the limit.",
    ))
    assert "R3:rationale_contradicts_evidence" in f.rule_references


def test_r3_consistent_finding_no_rule_reference():
    f, _ = review_finding(_make(
        rationale="The substance fails the specification.",
        evidence="Results fail the limit.",
    ))
    assert "R3:rationale_contradicts_evidence" not in f.rule_references


# ---------------------------------------------------------------------------
# R4 — S.5 missing lot number
# ---------------------------------------------------------------------------

def test_r4_missing_lot_sets_rule_reference():
    # Remove "lot" but keep other markers so R7 does not fire
    f, _ = review_finding(_s5(
        rationale="CoA submitted. Working standard qualified against primary. Source: USP.",
        evidence="Certificate of analysis confirmed.",
    ))
    assert "R4:s5_missing_lot_number" in f.rule_references


def test_r4_lot_present_no_rule_reference():
    f, _ = review_finding(_s5())  # default rationale has "lot"
    assert "R4:s5_missing_lot_number" not in f.rule_references


# ---------------------------------------------------------------------------
# R5 — S.5 CoA not referenced
# ---------------------------------------------------------------------------

def test_r5_missing_coa_sets_rule_reference():
    # Remove CoA keywords but keep other markers
    f, _ = review_finding(_s5(
        rationale="Lot R09060 used. Working standard qualified against primary. Source: USP.",
        evidence="Reference standard lot R09060 confirmed compliant.",
    ))
    assert "R5:s5_coa_not_referenced" in f.rule_references


def test_r5_coa_present_no_rule_reference():
    f, _ = review_finding(_s5())
    assert "R5:s5_coa_not_referenced" not in f.rule_references


# ---------------------------------------------------------------------------
# R5b — S.5 overlaid IR spectra not referenced
# ---------------------------------------------------------------------------

def test_r5b_missing_ir_sets_rule_reference():
    # CoA and all other IPRP markers present, but no IR keyword
    f, _ = review_finding(_s5(
        rationale="Lot R09060 used. CoA submitted. Working standard qualified against primary. Source: USP.",
        evidence="Certificate of analysis on file. Lot R09060 confirmed.",
    ))
    assert "R5b:s5_ir_spectra_not_referenced" in f.rule_references


def test_r5b_ir_keyword_present_no_rule_reference():
    # Default _s5() now includes IR keywords — R5b must NOT fire
    f, _ = review_finding(_s5())
    assert "R5b:s5_ir_spectra_not_referenced" not in f.rule_references


def test_r5b_infrared_spelling_accepted():
    f, _ = review_finding(_s5(
        rationale="Lot R09060. CoA submitted. Infrared spectra submitted. Working standard qualified. Source: USP.",
        evidence="Infrared spectrum confirmed identity.",
    ))
    assert "R5b:s5_ir_spectra_not_referenced" not in f.rule_references


def test_r5b_overlaid_spelling_accepted():
    f, _ = review_finding(_s5(
        rationale="Lot R09060. CoA submitted. Overlaid spectra submitted. Working standard qualified. Source: USP.",
        evidence="Spectra overlaid and consistent.",
    ))
    assert "R5b:s5_ir_spectra_not_referenced" not in f.rule_references


def test_r5b_r7_early_return_excludes_r5b():
    """R7 fires first on a blank S.5 — R5b must not appear in rule_references."""
    f, _ = review_finding(_s5(
        rationale="No information has been provided.",
        evidence="Section is empty.",
    ))
    assert "R5b:s5_ir_spectra_not_referenced" not in f.rule_references
    assert f.qa_status == "ESCALATE"


# ---------------------------------------------------------------------------
# R6 — S.5 working standard not referenced
# ---------------------------------------------------------------------------

def test_r6_missing_ws_sets_rule_reference():
    # Remove working standard keywords but keep other markers
    f, _ = review_finding(_s5(
        rationale="Lot R09060 used. CoA submitted. Source: USP.",
        evidence="Reference standard lot R09060; certificate of analysis on file.",
    ))
    assert "R6:s5_working_std_not_referenced" in f.rule_references


def test_r6_ws_present_no_rule_reference():
    f, _ = review_finding(_s5())
    assert "R6:s5_working_std_not_referenced" not in f.rule_references


# ---------------------------------------------------------------------------
# R7 — blank S.5 section (direct escalation)
# ---------------------------------------------------------------------------

def test_r7_blank_s5_sets_rule_reference():
    f, _ = review_finding(_s5(
        rationale="No information has been provided.",
        evidence="Section is empty.",
    ))
    assert "R7:s5_section_not_completed" in f.rule_references
    assert f.qa_status == "ESCALATE"


def test_r7_does_not_set_other_s5_rules():
    """When R7 fires, the function returns early — R4/R5/R5b/R6 must not also appear."""
    f, _ = review_finding(_s5(
        rationale="No information has been provided.",
        evidence="Section is empty.",
    ))
    assert "R4:s5_missing_lot_number" not in f.rule_references
    assert "R5:s5_coa_not_referenced" not in f.rule_references
    assert "R5b:s5_ir_spectra_not_referenced" not in f.rule_references
    assert "R6:s5_working_std_not_referenced" not in f.rule_references


# ---------------------------------------------------------------------------
# Multiple rules on same finding
# ---------------------------------------------------------------------------

def test_r1_and_r2_both_appear():
    f, _ = review_finding(_make(citation="", uncertainty_score=200))
    assert "R1:missing_citation" in f.rule_references
    assert "R2:uncertainty_out_of_range" in f.rule_references


def test_r4_and_r5_both_appear():
    # lot AND coa missing, but working standard and source present
    f, _ = review_finding(_s5(
        rationale="Working standard qualified against primary standard. Source: USP.",
        evidence="Secondary standard sourced from ABC unit.",
    ))
    assert "R4:s5_missing_lot_number" in f.rule_references
    assert "R5:s5_coa_not_referenced" in f.rule_references
    # R5b also fires here (no IR keyword) — confirm it appears too
    assert "R5b:s5_ir_spectra_not_referenced" in f.rule_references


# ---------------------------------------------------------------------------
# Section-escalation promotion preserves rule_references
# ---------------------------------------------------------------------------

def test_section_escalation_preserves_rule_references():
    """
    Two FLAG findings in the same section are promoted to ESCALATE by the
    section rule.  Their rule_references must survive the promotion.
    """
    f1 = _make("F-1", ctd_section="3.2.S.3", citation="")        # R1 → FLAG
    f2 = _make("F-2", ctd_section="3.2.S.3", uncertainty_score=999)  # R2 → FLAG
    reviewed = review_findings([f1, f2])

    r1_out = next(f for f in reviewed if f.finding_id == "F-1")
    r2_out = next(f for f in reviewed if f.finding_id == "F-2")

    # Both promoted to ESCALATE by the section rule
    assert r1_out.qa_status == "ESCALATE"
    assert r2_out.qa_status == "ESCALATE"

    # rule_references must still be set correctly
    assert "R1:missing_citation" in r1_out.rule_references
    assert "R2:uncertainty_out_of_range" in r2_out.rule_references


# ---------------------------------------------------------------------------
# review_finding (single-finding public helper) also sets rule_references
# ---------------------------------------------------------------------------

def test_review_finding_helper_sets_rule_references():
    f, reasons = review_finding(_make(citation=""))
    assert "R1:missing_citation" in f.rule_references
    assert len(reasons) == 1
    assert reasons[0].code == "missing_citation"


# ---------------------------------------------------------------------------
# rule_references is a plain list of strings (serialisable)
# ---------------------------------------------------------------------------

def test_rule_references_are_strings():
    f, _ = review_finding(_make(citation="", uncertainty_score=999))
    assert all(isinstance(r, str) for r in f.rule_references)


def test_rule_references_format():
    """Each label must follow 'R<n[letter]>:<code>' convention, e.g. R1, R5, R5b."""
    import re
    f, _ = review_finding(_make(citation="", uncertainty_score=999))
    for ref in f.rule_references:
        assert re.match(r"^R[\da-z]+:[a-z_]+$", ref), (
            f"rule_reference {ref!r} does not match expected 'R<n>:<code>' format"
        )
