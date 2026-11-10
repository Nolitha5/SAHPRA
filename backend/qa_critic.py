"""
QA/Critic agent — deterministic, rule-based.

Rules applied to each Finding:
  R1. citation must be non-empty (structural check only; factual accuracy is NOT verified)
  R2. uncertainty_score must be in [0, 100]
  R3. rationale tone must not obviously contradict evidence tone (surface-level heuristic)

S.5-specific rules applied when ctd_section == "3.2.S.5":
  R4. lot/batch number must be present for compendial standard claims
  R5. CoA submission must be stated (True or False — omission is the problem)
  R6. Working standard qualification against primary must be stated
  R7. If ALL four IPRP sub-item fields (lot, coa, working_std, source_detail) are absent,
      escalate directly — this is the "applicant left S.5 blank in SCoRE" scenario.

Escalation rules:
  - R7 (blank S.5 section): immediate ESCALATE on that finding.
  - Section rule: if 2 or more findings in the same CTD section are FLAG,
    every flagged finding in that section is promoted to ESCALATE.

This module never invents citations, removes findings, or makes regulatory conclusions.
Every finding is returned with an explicit qa_status.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import NamedTuple

from models import Finding

UNCERTAINTY_MIN = 0
UNCERTAINTY_MAX = 100

# Keyword sets for the surface-level consistency heuristic (R3).
# Keywords are matched as whole words (regex \b boundaries) to avoid
# false positives such as "match" matching inside "mismatch".
_COMPLIANCE_WORDS = (
    "matches", "meets", "within", "complies", "compliant",
    "confirmed", "acceptable", "within limits",
)
_NON_COMPLIANCE_WORDS = (
    "does not match", "does not meet", "mismatch", "incorrect", "outdated",
    "exceeds", "fails", "non-compliant", "not within", "discrepancy",
)


def _contains(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(re.search(r'\b' + re.escape(kw) + r'\b', lowered) for kw in keywords)


def _rationale_contradicts_evidence(rationale: str, evidence: str) -> bool:
    """
    Surface-level heuristic only — detects obvious tone mismatch.
    Cannot verify factual or regulatory accuracy.

    Returns True in two cases:
      - Rationale asserts compliance while evidence signals a problem.
      - Rationale asserts non-compliance while evidence signals compliance only.
    """
    rat_ok   = _contains(rationale, _COMPLIANCE_WORDS)
    rat_fail = _contains(rationale, _NON_COMPLIANCE_WORDS)
    ev_ok    = _contains(evidence,  _COMPLIANCE_WORDS)
    ev_fail  = _contains(evidence,  _NON_COMPLIANCE_WORDS)

    if rat_ok and not rat_fail and ev_fail and not ev_ok:
        return True
    if rat_fail and not rat_ok and ev_ok and not ev_fail:
        return True
    return False


class FlagReason(NamedTuple):
    code: str
    detail: str


def _check_finding(finding: Finding) -> tuple[list[FlagReason], bool]:
    """
    Apply all QA rules to a single finding.

    Returns:
      (reasons, direct_escalate)
      - reasons:          list of FlagReasons (empty = PASS)
      - direct_escalate:  True if R7 fires — bypass normal FLAG/PASS and go
                          straight to ESCALATE regardless of section count.
    """
    reasons: list[FlagReason] = []
    direct_escalate = False

    # ── R1: citation presence ─────────────────────────────────────────────
    if not finding.citation or not finding.citation.strip():
        reasons.append(FlagReason(
            code="missing_citation",
            detail="citation field is empty; structural presence required",
        ))

    # ── R2: uncertainty score range ───────────────────────────────────────
    if not (UNCERTAINTY_MIN <= finding.uncertainty_score <= UNCERTAINTY_MAX):
        reasons.append(FlagReason(
            code="uncertainty_out_of_range",
            detail=(
                f"uncertainty_score {finding.uncertainty_score} is outside "
                f"[{UNCERTAINTY_MIN}, {UNCERTAINTY_MAX}]"
            ),
        ))

    # ── R3: surface consistency ───────────────────────────────────────────
    if _rationale_contradicts_evidence(finding.rationale, finding.evidence_snippet):
        reasons.append(FlagReason(
            code="rationale_contradicts_evidence",
            detail="rationale tone contradicts evidence tone (surface heuristic)",
        ))

    # ── S.5-specific rules (R4–R7) ────────────────────────────────────────
    # These only fire when the finding is tagged to section 3.2.S.5.
    # They inspect the finding's rationale/evidence for the presence of
    # required IPRP sub-item information.
    #
    # Design note: the QA/Critic does not hold S5Claim objects — it receives
    # Finding objects from the pipeline.  The Finding's rationale and
    # evidence_snippet are the only source of S.5 content visible here.
    # R4–R7 therefore check for the *absence* of IPRP-required keywords in
    # those fields, acting as a last-line structural catch.
    #
    # For richer S.5 validation (edition compliance, lot lookup) the upstream
    # S.5 agent (s5_standards.py / check_s5_claim) is the authoritative check.

    if finding.ctd_section == "3.2.S.5":

        # ── R7: blank S.5 submission (highest priority) ──────────────────
        # If none of the four IPRP sub-item keywords appear anywhere in the
        # combined rationale + evidence, treat the section as not completed.
        # Mirrors the real-world scenario: "Applicant has not included the
        # required information in the SCoRE."  Direct escalation, not a simple FLAG.
        s5_text = (finding.rationale + " " + finding.evidence_snippet).lower()
        iprp_markers = [
            "lot",          # sub-item (a): lot/batch number
            "coa",          # sub-item (b): certificate of analysis
            "certificate",  # sub-item (b): alternative spelling
            "working standard",   # sub-item (c)
            "secondary standard", # sub-item (c): alternative phrasing
            "source",       # sub-item (d): source of standards
        ]
        if not any(marker in s5_text for marker in iprp_markers):
            reasons.append(FlagReason(
                code="s5_section_not_completed",
                detail=(
                    "3.2.S.5 finding contains none of the required IPRP sub-item "
                    "indicators (lot number, CoA, working standard, source). "
                    "Applicant may not have included the required information in SCoRE."
                ),
            ))
            direct_escalate = True
            # Return early — no point adding more flags on a blank submission
            return reasons, direct_escalate

        # ── R4: lot/batch number ─────────────────────────────────────────
        # IPRP sub-item (a): batch number required for all primary standards.
        if not re.search(r'\blot\b|\bbatch\b', s5_text):
            reasons.append(FlagReason(
                code="s5_missing_lot_number",
                detail=(
                    "3.2.S.5: lot/batch number of the primary reference standard "
                    "not referenced in this finding (IPRP sub-item a)"
                ),
            ))

        # ── R5: CoA submission ───────────────────────────────────────────
        # IPRP sub-item (b): CoA (and overlaid IR spectra) submission must be stated.
        if not re.search(r'\bcoa\b|\bcertificate of analysis\b', s5_text):
            reasons.append(FlagReason(
                code="s5_coa_not_referenced",
                detail=(
                    "3.2.S.5: certificate of analysis (CoA) not referenced in this "
                    "finding (IPRP sub-item b)"
                ),
            ))

        # ── R6: working standard qualification ──────────────────────────
        # IPRP sub-item (c): secondary standard must be standardised against
        # the compendial or primary reference standard.
        if not re.search(r'\bworking standard\b|\bsecondary standard\b|\bws\b', s5_text):
            reasons.append(FlagReason(
                code="s5_working_std_not_referenced",
                detail=(
                    "3.2.S.5: working/secondary standard qualification not referenced "
                    "in this finding (IPRP sub-item c)"
                ),
            ))

    return reasons, direct_escalate


def _review_finding_with_escalation(
    finding: Finding,
) -> tuple[Finding, list[FlagReason], bool]:
    reasons, direct_escalate = _check_finding(finding)

    if direct_escalate:
        status = "ESCALATE"
    elif reasons:
        status = "FLAG"
    else:
        status = "PASS"

    return finding.model_copy(update={"qa_status": status}), reasons, direct_escalate


def review_finding(finding: Finding) -> tuple[Finding, list[FlagReason]]:
    """
    Apply QA rules to one finding.
    Returns the updated Finding (qa_status set) and the list of flag reasons.
    """
    reviewed, reasons, _ = _review_finding_with_escalation(finding)
    return reviewed, reasons


def review_findings(findings: list[Finding]) -> list[Finding]:
    """
    Review a list of findings.

    Steps:
      1. Apply per-finding rules; assign PASS, FLAG, or direct ESCALATE (R7).
      2. Count flags per CTD section (direct escalations are not counted here —
         they already have their final status).
      3. Promote all FLAG findings in any section with ≥ 2 flags to ESCALATE.

    All findings are returned — none are removed or suppressed.
    """
    reviewed_triples = [_review_finding_with_escalation(f) for f in findings]

    # Count ordinary FLAGs per section (exclude direct escalations from count)
    flag_counts: Counter[str] = Counter(
        f.ctd_section
        for f, _, direct in reviewed_triples
        if f.qa_status == "FLAG" and not direct
    )

    result: list[Finding] = []
    for f, _, direct in reviewed_triples:
        if direct:
            # R7 direct escalation — keep as-is
            result.append(f)
        elif f.qa_status == "FLAG" and flag_counts[f.ctd_section] >= 2:
            result.append(f.model_copy(update={"qa_status": "ESCALATE"}))
        else:
            result.append(f)

    return result
