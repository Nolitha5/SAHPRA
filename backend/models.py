from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel


class Finding(BaseModel):
    finding_id: str
    ctd_section: str  # e.g. "3.2.S.1", "3.2.S.5"
    rationale: str
    evidence_snippet: str
    # Structural presence is checked; factual accuracy is NOT verified here.
    citation: str
    # 0 = certain, 100 = maximally uncertain; range enforcement is done by QA/Critic
    uncertainty_score: int
    qa_status: Optional[Literal["PASS", "FLAG", "ESCALATE"]] = None
    assessor_decision: Optional[Literal["Approve", "Query", "Reject"]] = None
    disposition_note: Optional[str] = None
    decision_timestamp: Optional[datetime] = None


class AssessorDecisionRequest(BaseModel):
    finding_id: str
    decision: Literal["Approve", "Query", "Reject"]
    disposition_note: Optional[str] = None


# ── S.5 Reference Standards models ───────────────────────────────────

class S5Claim(BaseModel):
    """Structured S.5 sponsor claim extracted from the dossier (supplied by M3)."""
    substance_name: str
    standard: str          # e.g. "BP", "USP", "Ph.Eur.", "IP"
    edition_claimed: str   # e.g. "BP 2019"
    test_method: Optional[str] = None
    submission_date: date


class S5Finding(BaseModel):
    """
    Result of the S.5 Reference Standards check.

    verdict:
      COMPLIANT     — claimed edition matches the current edition at submission date.
      NON_COMPLIANT — a current edition was found but differs from the claimed edition.
      NEEDS_REVIEW  — authoritative reference information was unavailable; no verdict made.

    source_note always states whether reference data is real or mocked.
    """
    substance_name: str
    standard_claimed: str
    edition_claimed: str
    monograph_name: Optional[str] = None
    edition_current: Optional[str] = None
    evidence: str
    citation: Optional[str] = None
    verdict: Literal["COMPLIANT", "NON_COMPLIANT", "NEEDS_REVIEW"]
    verdict_reason: str
    source_note: str
