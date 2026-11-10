from __future__ import annotations

from datetime import date, datetime
from enum import Enum
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


# ── S.5 Reference Standards models ───────────────────────────────────────────
# Aligned with IPRP QWGG Guidance for Quality Assessors — Drug Substance,
# Section S.5 Reference Standards or Materials (page 17/22).
# Sub-items (a)–(d) map directly to the four checklist points in the QAR.


class ReferenceStandardType(str, Enum):
    """
    Whether the primary reference standard is a compendial standard
    (USP, BP, Ph.Eur., IP) or an in-house standard.
    IPRP: compendial standards do not need further structural elucidation;
    in-house standards must be fully characterised.
    """
    COMPENDIAL = "compendial"
    IN_HOUSE   = "in-house"
    OTHER      = "other"


class ImpurityStandard(BaseModel):
    """
    One named impurity reference standard.
    IPRP: characterisation + assigned purity required for each impurity standard.
    """
    name: str                                   # e.g. "Impurity-A", "Methyl ester analogue"
    source: str                                 # e.g. "ABC R&D Center (synthesised in-house)"
    purity_assigned: bool                       # Has an assigned purity value been declared?
    characterisation_methods: list[str]         # e.g. ["IR", "NMR", "MS"]


class S5Claim(BaseModel):
    """
    Structured S.5 sponsor claim extracted from the dossier (supplied by M3).

    Fields are grouped by the four IPRP QAR sub-items:
      (a) Primary standard — pharmacopoeial / in-house, lot number
      (b) CoA + overlaid IR spectra
      (c) Secondary (working) standard traceability
      (d) Source of standards used for identification, purity, potency tests
    Plus impurity standards (IPRP: if applicable).

    Optional fields that are None indicate the applicant did not provide that
    information.  The QA/Critic treats systematically absent fields as a
    completeness failure (R7).
    """
    # ── Core (always required) ────────────────────────────────────────────
    substance_name: str
    standard: str                               # "USP", "BP", "Ph.Eur.", "IP"
    edition_claimed: str                        # e.g. "USP 47", "BP 2024"
    submission_date: date
    test_method: Optional[str] = None           # e.g. "Purity by HPLC"

    # ── Sub-item (a): Primary reference standard ──────────────────────────
    # IPRP: "State the primary reference standard used: compendial or in-house;
    #         reference standard and batch number."
    standard_type: Optional[ReferenceStandardType] = None
    lot_number: Optional[str] = None            # e.g. "R09060"  (USP lot used in Amlodipine case)

    # In-house primary only:
    # IPRP: "If a primary in-house reference standard is used, state if it is
    #         fully characterised (e.g., IR, UV, NMR, MS). State if a certificate
    #         of analysis has been submitted with purity assigned based on mass
    #         balance or a determination of absolute purity."
    inhouse_characterisation_methods: Optional[list[str]] = None  # ["IR","UV","NMR","MS"]
    inhouse_purity_assigned: Optional[bool] = None
    inhouse_coa_submitted: Optional[bool] = None

    # ── Sub-item (b): CoA + overlaid IR spectra ───────────────────────────
    # IPRP / real dossier checklist point (b):
    # "State if a certificate of analysis and overlaid IR spectra have been submitted."
    coa_submitted: Optional[bool] = None
    ir_spectra_submitted: Optional[bool] = None

    # ── Sub-item (c): Secondary / working standard ────────────────────────
    # IPRP: "State if a secondary reference standard (e.g. working standard) is
    #         standardised against the compendial reference standard or primary
    #         reference standard."
    # Real dossier: WS no. HDL1/ABWS/20/1 qualified against USPRS Lot R09060.
    working_standard_lot: Optional[str] = None             # e.g. "HDL1/ABWS/20/1"
    working_standard_source: Optional[str] = None          # e.g. "ABC Unit-7"
    working_std_qualified_against_primary: Optional[bool] = None

    # ── Sub-item (d): Source of reference standards for testing ──────────
    # IPRP: "The source(s) of the reference standards or materials used in the
    #         testing of the drug substance (identification, purity, potency tests).
    #         If Ph.Eur. reference standard is used for quantitative analysis,
    #         it should be for content, not identity only."
    reference_standard_source_detail: Optional[str] = None  # e.g. "Purchased from USP"
    ph_eur_used_for_content: Optional[bool] = None           # Relevant only when standard=Ph.Eur.

    # ── Impurity standards ────────────────────────────────────────────────
    # IPRP: "Impurity standard (characterisation, purity), if applicable."
    impurity_standards: Optional[list[ImpurityStandard]] = None


class S5Finding(BaseModel):
    """
    Result of the S.5 Reference Standards check.

    verdict:
      COMPLIANT          — claimed edition matches the current edition at submission date.
      NON_COMPLIANT      — a current edition was found but differs from the claimed edition.
      NEEDS_REVIEW       — authoritative reference information was unavailable; no verdict made.

    completeness_flags:
      List of field names that are missing but required by IPRP.
      Empty list means the submission is structurally complete.

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
    # New: list of IPRP checklist items missing from the claim
    completeness_flags: list[str] = []
