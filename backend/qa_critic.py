"""
QA/Critic agent — deterministic, rule-based.

Rules applied to each Finding:
  R1. citation must be non-empty (structural check only; factual accuracy is NOT verified)
  R2. uncertainty_score must be in [0, 100]
  R3. rationale tone must not obviously contradict evidence tone (surface-level heuristic)

Escalation rule:
  If 2 or more findings in the same CTD section are FLAG, every flagged finding
  in that section is promoted to ESCALATE.

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


def _check_finding(finding: Finding) -> list[FlagReason]:
    reasons: list[FlagReason] = []

    # R1 — citation presence
    if not finding.citation or not finding.citation.strip():
        reasons.append(FlagReason(
            code="missing_citation",
            detail="citation field is empty; structural presence required",
        ))

    # R2 — score range
    if not (UNCERTAINTY_MIN <= finding.uncertainty_score <= UNCERTAINTY_MAX):
        reasons.append(FlagReason(
            code="uncertainty_out_of_range",
            detail=(
                f"uncertainty_score {finding.uncertainty_score} is outside "
                f"[{UNCERTAINTY_MIN}, {UNCERTAINTY_MAX}]"
            ),
        ))

    # R3 — surface consistency
    if _rationale_contradicts_evidence(finding.rationale, finding.evidence_snippet):
        reasons.append(FlagReason(
            code="rationale_contradicts_evidence",
            detail="rationale tone contradicts evidence tone (surface heuristic)",
        ))

    return reasons


def review_finding(finding: Finding) -> tuple[Finding, list[FlagReason]]:
    """
    Apply QA rules to one finding.
    Returns the updated Finding (qa_status set) and the list of flag reasons.
    """
    reasons = _check_finding(finding)
    status = "FLAG" if reasons else "PASS"
    return finding.model_copy(update={"qa_status": status}), reasons


def review_findings(findings: list[Finding]) -> list[Finding]:
    """
    Review a list of findings.

    Steps:
      1. Apply per-finding rules; assign PASS or FLAG.
      2. Count flags per CTD section.
      3. Escalate all flagged findings in any section with ≥ 2 flags.

    All findings are returned — none are removed or suppressed.
    """
    reviewed_pairs = [review_finding(f) for f in findings]
    reviewed = [f for f, _ in reviewed_pairs]

    flag_counts: Counter[str] = Counter(
        f.ctd_section for f in reviewed if f.qa_status == "FLAG"
    )

    result: list[Finding] = []
    for f in reviewed:
        if f.qa_status == "FLAG" and flag_counts[f.ctd_section] >= 2:
            result.append(f.model_copy(update={"qa_status": "ESCALATE"}))
        else:
            result.append(f)

    return result
