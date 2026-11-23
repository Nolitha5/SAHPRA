"""
S.5 Reference Standards agent.

Accepts a structured S5Claim and a MonographRepository, then:
  1. Checks completeness against the IPRP QWGG S.5 checklist (sub-items a–d).
  2. Looks up the pharmacopoeial monograph current at the submission date.
  3. Compares the sponsor's claimed edition to the retrieved current edition.
  4. Derives evidence_sufficiency from verdict + completeness_flags (Phase 4).
  5. Optionally calls the Ollama LLM for reasoning commentary (Phase 5).
  6. Returns an S5Finding with:
       - verdict: COMPLIANT, NON_COMPLIANT, or NEEDS_REVIEW
       - completeness_flags: list of IPRP checklist items the applicant left blank
       - evidence_sufficiency: categorised classification of evidence quality
       - model_review: AI reasoning commentary (when ollama_enabled=True)

MonographRepository is a Protocol (replaceable interface).  The mock
implementation (MockMonographRepository) uses explicitly labelled in-memory
records and is the only implementation used until M2's RKB is available.

This module NEVER invents monograph names, edition numbers, citations or
regulatory conclusions.  If the required information is not available it
returns NEEDS_REVIEW with a clear explanation.

IPRP reference: IPRP QWGG Guidance for Quality Assessors – Drug Substance,
Section S.5 Reference Standards or Materials (page 17/22).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from models import ReferenceStandardType, S5Claim, S5Finding
from retrieval import WebMonographRepository as _WebMonographRepository

logger = logging.getLogger(__name__)


# ── Replaceable interface ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class MonographRecord:
    """A single pharmacopoeial monograph record as supplied by a repository."""
    standard: str        # "BP", "USP", "Ph.Eur.", "IP"
    substance_name: str  # normalised lower-case
    edition: str         # e.g. "BP 2024"
    valid_from: date     # first date this edition was current
    monograph_name: str  # official monograph title
    page: str | None     # page reference if known
    source_note: str     # MUST state whether real or mock data


class MonographRepository(Protocol):
    """
    Replaceable interface for retrieving pharmacopoeial monographs.

    Implementations:
      - MockMonographRepository  (this file) — used until M2 provides a real RKB.
      - M2RKBRepository          (future)    — wraps M2's retrieval API.
    """

    def get_current_edition(
        self,
        standard: str,
        substance_name: str,
        as_of: date,
    ) -> MonographRecord | None:
        """
        Return the monograph record that was current for the given standard and
        substance on `as_of`.  Return None if no record is available.
        """
        ...


# ── Mock implementation ───────────────────────────────────────────────────────

_MOCK_NOTE = "MOCK DATA — not from a real pharmacopoeia; for development only"

# Each tuple represents one edition entry.  To find what was current on a
# given date, the repository selects the record with the greatest valid_from
# that is still <= as_of.
_MOCK_RECORDS: list[MonographRecord] = [

    # ── British Pharmacopoeia — Ethanol ───────────────────────────────
    MonographRecord(
        standard="BP", substance_name="ethanol",
        edition="BP 2019", valid_from=date(2019, 1, 1),
        monograph_name="Ethanol", page="812",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="BP", substance_name="ethanol",
        edition="BP 2020", valid_from=date(2020, 1, 1),
        monograph_name="Ethanol", page="831",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="BP", substance_name="ethanol",
        edition="BP 2024", valid_from=date(2024, 1, 1),
        monograph_name="Ethanol", page="856",
        source_note=_MOCK_NOTE,
    ),

    # ── Ph. Eur. — Ethanol ────────────────────────────────────────────
    MonographRecord(
        standard="Ph.Eur.", substance_name="ethanol",
        edition="Ph.Eur. 10.0", valid_from=date(2020, 1, 1),
        monograph_name="Ethanol", page="1812",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="Ph.Eur.", substance_name="ethanol",
        edition="Ph.Eur. 11.0", valid_from=date(2023, 1, 1),
        monograph_name="Ethanol", page="1904",
        source_note=_MOCK_NOTE,
    ),

    # ── Indian Pharmacopoeia — Ethanol ────────────────────────────────
    MonographRecord(
        standard="IP", substance_name="ethanol",
        edition="IP 2022", valid_from=date(2022, 1, 1),
        monograph_name="Ethanol", page="634",
        source_note=_MOCK_NOTE,
    ),

    # ── United States Pharmacopeia — Aspirin ──────────────────────────
    MonographRecord(
        standard="USP", substance_name="aspirin",
        edition="USP 42", valid_from=date(2019, 5, 1),
        monograph_name="Aspirin", page="1204",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="USP", substance_name="aspirin",
        edition="USP 47", valid_from=date(2024, 5, 1),
        monograph_name="Aspirin", page="1251",
        source_note=_MOCK_NOTE,
    ),

    # ── British Pharmacopoeia — Aspirin ───────────────────────────────
    MonographRecord(
        standard="BP", substance_name="aspirin",
        edition="BP 2022", valid_from=date(2022, 1, 1),
        monograph_name="Aspirin", page="244",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="BP", substance_name="aspirin",
        edition="BP 2024", valid_from=date(2024, 1, 1),
        monograph_name="Aspirin", page="251",
        source_note=_MOCK_NOTE,
    ),

    # ── Ph. Eur. — Aspirin (Acidum Acetylsalicylicum) ─────────────────
    MonographRecord(
        standard="Ph.Eur.", substance_name="aspirin",
        edition="Ph.Eur. 10.0", valid_from=date(2020, 1, 1),
        monograph_name="Acidum Acetylsalicylicum", page="1521",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="Ph.Eur.", substance_name="aspirin",
        edition="Ph.Eur. 11.0", valid_from=date(2023, 1, 1),
        monograph_name="Acidum Acetylsalicylicum", page="1601",
        source_note=_MOCK_NOTE,
    ),

    # ── United States Pharmacopeia — Amlodipine Besylate ─────────────
    # Based on real dossier: USP lot R09060.
    MonographRecord(
        standard="USP", substance_name="amlodipine besylate",
        edition="USP 46", valid_from=date(2023, 5, 1),
        monograph_name="Amlodipine Besylate", page="502",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="USP", substance_name="amlodipine besylate",
        edition="USP 47", valid_from=date(2024, 5, 1),
        monograph_name="Amlodipine Besylate", page="518",
        source_note=_MOCK_NOTE,
    ),

    # ── British Pharmacopoeia — Amlodipine Besilate ───────────────────
    MonographRecord(
        standard="BP", substance_name="amlodipine besylate",
        edition="BP 2022", valid_from=date(2022, 1, 1),
        monograph_name="Amlodipine Besilate", page="104",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="BP", substance_name="amlodipine besylate",
        edition="BP 2024", valid_from=date(2024, 1, 1),
        monograph_name="Amlodipine Besilate", page="109",
        source_note=_MOCK_NOTE,
    ),

    # ── Ph. Eur. — Amlodipine Besilate ───────────────────────────────
    MonographRecord(
        standard="Ph.Eur.", substance_name="amlodipine besylate",
        edition="Ph.Eur. 10.0", valid_from=date(2020, 1, 1),
        monograph_name="Amlodipini besilas", page="1710",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="Ph.Eur.", substance_name="amlodipine besylate",
        edition="Ph.Eur. 11.0", valid_from=date(2023, 1, 1),
        monograph_name="Amlodipini besilas", page="1798",
        source_note=_MOCK_NOTE,
    ),

    # ── Indian Pharmacopoeia — Amlodipine Besilate ────────────────────
    MonographRecord(
        standard="IP", substance_name="amlodipine besylate",
        edition="IP 2022", valid_from=date(2022, 1, 1),
        monograph_name="Amlodipine Besilate", page="284",
        source_note=_MOCK_NOTE,
    ),

    # ── United States Pharmacopeia — Valsartan ────────────────────────
    # SCoRE fixed-dose combination test cases (Amlodipine/Valsartan/HCTZ).
    MonographRecord(
        standard="USP", substance_name="valsartan",
        edition="USP 46", valid_from=date(2023, 5, 1),
        monograph_name="Valsartan", page="6421",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="USP", substance_name="valsartan",
        edition="USP 47", valid_from=date(2024, 5, 1),
        monograph_name="Valsartan", page="6589",
        source_note=_MOCK_NOTE,
    ),

    # ── British Pharmacopoeia — Valsartan ─────────────────────────────
    MonographRecord(
        standard="BP", substance_name="valsartan",
        edition="BP 2023", valid_from=date(2023, 1, 1),
        monograph_name="Valsartan", page="2814",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="BP", substance_name="valsartan",
        edition="BP 2024", valid_from=date(2024, 1, 1),
        monograph_name="Valsartan", page="2887",
        source_note=_MOCK_NOTE,
    ),

    # ── United States Pharmacopeia — Hydrochlorothiazide ─────────────
    # SCoRE fixed-dose combination test cases.
    MonographRecord(
        standard="USP", substance_name="hydrochlorothiazide",
        edition="USP 46", valid_from=date(2023, 5, 1),
        monograph_name="Hydrochlorothiazide", page="3214",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="USP", substance_name="hydrochlorothiazide",
        edition="USP 47", valid_from=date(2024, 5, 1),
        monograph_name="Hydrochlorothiazide", page="3301",
        source_note=_MOCK_NOTE,
    ),

    # ── British Pharmacopoeia — Hydrochlorothiazide ───────────────────
    MonographRecord(
        standard="BP", substance_name="hydrochlorothiazide",
        edition="BP 2022", valid_from=date(2022, 1, 1),
        monograph_name="Hydrochlorothiazide", page="1104",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="BP", substance_name="hydrochlorothiazide",
        edition="BP 2024", valid_from=date(2024, 1, 1),
        monograph_name="Hydrochlorothiazide", page="1142",
        source_note=_MOCK_NOTE,
    ),

    # ── Ph. Eur. — Hydrochlorothiazide ───────────────────────────────
    MonographRecord(
        standard="Ph.Eur.", substance_name="hydrochlorothiazide",
        edition="Ph.Eur. 11.0", valid_from=date(2023, 1, 1),
        monograph_name="Hydrochlorothiazidum", page="3214",
        source_note=_MOCK_NOTE,
    ),

    # ── United States Pharmacopeia — Metformin Hydrochloride ─────────
    MonographRecord(
        standard="USP", substance_name="metformin hydrochloride",
        edition="USP 46", valid_from=date(2023, 5, 1),
        monograph_name="Metformin Hydrochloride", page="4102",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="USP", substance_name="metformin hydrochloride",
        edition="USP 47", valid_from=date(2024, 5, 1),
        monograph_name="Metformin Hydrochloride", page="4211",
        source_note=_MOCK_NOTE,
    ),

    # ── British Pharmacopoeia — Metformin Hydrochloride ───────────────
    MonographRecord(
        standard="BP", substance_name="metformin hydrochloride",
        edition="BP 2023", valid_from=date(2023, 1, 1),
        monograph_name="Metformin Hydrochloride", page="1521",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="BP", substance_name="metformin hydrochloride",
        edition="BP 2024", valid_from=date(2024, 1, 1),
        monograph_name="Metformin Hydrochloride", page="1562",
        source_note=_MOCK_NOTE,
    ),

    # ── Ph. Eur. — Metformin Hydrochloride ───────────────────────────
    MonographRecord(
        standard="Ph.Eur.", substance_name="metformin hydrochloride",
        edition="Ph.Eur. 10.0", valid_from=date(2020, 1, 1),
        monograph_name="Metformini hydrochloridum", page="2914",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="Ph.Eur.", substance_name="metformin hydrochloride",
        edition="Ph.Eur. 11.0", valid_from=date(2023, 1, 1),
        monograph_name="Metformini hydrochloridum", page="3012",
        source_note=_MOCK_NOTE,
    ),

    # ── Indian Pharmacopoeia — Metformin Hydrochloride ────────────────
    MonographRecord(
        standard="IP", substance_name="metformin hydrochloride",
        edition="IP 2022", valid_from=date(2022, 1, 1),
        monograph_name="Metformin Hydrochloride", page="1104",
        source_note=_MOCK_NOTE,
    ),

    # ── United States Pharmacopeia — Atenolol ─────────────────────────
    MonographRecord(
        standard="USP", substance_name="atenolol",
        edition="USP 46", valid_from=date(2023, 5, 1),
        monograph_name="Atenolol", page="1512",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="USP", substance_name="atenolol",
        edition="USP 47", valid_from=date(2024, 5, 1),
        monograph_name="Atenolol", page="1584",
        source_note=_MOCK_NOTE,
    ),

    # ── British Pharmacopoeia — Atenolol ──────────────────────────────
    MonographRecord(
        standard="BP", substance_name="atenolol",
        edition="BP 2022", valid_from=date(2022, 1, 1),
        monograph_name="Atenolol", page="192",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="BP", substance_name="atenolol",
        edition="BP 2024", valid_from=date(2024, 1, 1),
        monograph_name="Atenolol", page="198",
        source_note=_MOCK_NOTE,
    ),

    # ── Ph. Eur. — Atenolol ───────────────────────────────────────────
    MonographRecord(
        standard="Ph.Eur.", substance_name="atenolol",
        edition="Ph.Eur. 11.0", valid_from=date(2023, 1, 1),
        monograph_name="Atenololum", page="1612",
        source_note=_MOCK_NOTE,
    ),

    # ── United States Pharmacopeia — Paracetamol ──────────────────────
    # Paracetamol is listed as "Acetaminophen" in USP.
    MonographRecord(
        standard="USP", substance_name="paracetamol",
        edition="USP 46", valid_from=date(2023, 5, 1),
        monograph_name="Acetaminophen", page="104",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="USP", substance_name="paracetamol",
        edition="USP 47", valid_from=date(2024, 5, 1),
        monograph_name="Acetaminophen", page="112",
        source_note=_MOCK_NOTE,
    ),

    # ── British Pharmacopoeia — Paracetamol ───────────────────────────
    MonographRecord(
        standard="BP", substance_name="paracetamol",
        edition="BP 2022", valid_from=date(2022, 1, 1),
        monograph_name="Paracetamol", page="1687",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="BP", substance_name="paracetamol",
        edition="BP 2024", valid_from=date(2024, 1, 1),
        monograph_name="Paracetamol", page="1724",
        source_note=_MOCK_NOTE,
    ),

    # ── Ph. Eur. — Paracetamol ────────────────────────────────────────
    MonographRecord(
        standard="Ph.Eur.", substance_name="paracetamol",
        edition="Ph.Eur. 10.0", valid_from=date(2020, 1, 1),
        monograph_name="Paracetamolum", page="3814",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="Ph.Eur.", substance_name="paracetamol",
        edition="Ph.Eur. 11.0", valid_from=date(2023, 1, 1),
        monograph_name="Paracetamolum", page="3904",
        source_note=_MOCK_NOTE,
    ),

    # ── Indian Pharmacopoeia — Paracetamol ────────────────────────────
    MonographRecord(
        standard="IP", substance_name="paracetamol",
        edition="IP 2022", valid_from=date(2022, 1, 1),
        monograph_name="Paracetamol", page="1842",
        source_note=_MOCK_NOTE,
    ),

    # ── United States Pharmacopeia — Ciprofloxacin Hydrochloride ──────
    MonographRecord(
        standard="USP", substance_name="ciprofloxacin hydrochloride",
        edition="USP 46", valid_from=date(2023, 5, 1),
        monograph_name="Ciprofloxacin Hydrochloride", page="2104",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="USP", substance_name="ciprofloxacin hydrochloride",
        edition="USP 47", valid_from=date(2024, 5, 1),
        monograph_name="Ciprofloxacin Hydrochloride", page="2187",
        source_note=_MOCK_NOTE,
    ),

    # ── British Pharmacopoeia — Ciprofloxacin Hydrochloride ───────────
    MonographRecord(
        standard="BP", substance_name="ciprofloxacin hydrochloride",
        edition="BP 2022", valid_from=date(2022, 1, 1),
        monograph_name="Ciprofloxacin Hydrochloride", page="512",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="BP", substance_name="ciprofloxacin hydrochloride",
        edition="BP 2024", valid_from=date(2024, 1, 1),
        monograph_name="Ciprofloxacin Hydrochloride", page="524",
        source_note=_MOCK_NOTE,
    ),

    # ── Indian Pharmacopoeia — Ciprofloxacin Hydrochloride ────────────
    MonographRecord(
        standard="IP", substance_name="ciprofloxacin hydrochloride",
        edition="IP 2022", valid_from=date(2022, 1, 1),
        monograph_name="Ciprofloxacin Hydrochloride", page="512",
        source_note=_MOCK_NOTE,
    ),

    # ── United States Pharmacopeia — Lisinopril ───────────────────────
    MonographRecord(
        standard="USP", substance_name="lisinopril",
        edition="USP 46", valid_from=date(2023, 5, 1),
        monograph_name="Lisinopril", page="3904",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="USP", substance_name="lisinopril",
        edition="USP 47", valid_from=date(2024, 5, 1),
        monograph_name="Lisinopril", page="4012",
        source_note=_MOCK_NOTE,
    ),

    # ── British Pharmacopoeia — Lisinopril ────────────────────────────
    MonographRecord(
        standard="BP", substance_name="lisinopril",
        edition="BP 2022", valid_from=date(2022, 1, 1),
        monograph_name="Lisinopril", page="1412",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="BP", substance_name="lisinopril",
        edition="BP 2024", valid_from=date(2024, 1, 1),
        monograph_name="Lisinopril", page="1451",
        source_note=_MOCK_NOTE,
    ),

    # ── Ph. Eur. — Lisinopril ─────────────────────────────────────────
    MonographRecord(
        standard="Ph.Eur.", substance_name="lisinopril",
        edition="Ph.Eur. 10.0", valid_from=date(2020, 1, 1),
        monograph_name="Lisinoprilum dihydricum", page="3714",
        source_note=_MOCK_NOTE,
    ),
    MonographRecord(
        standard="Ph.Eur.", substance_name="lisinopril",
        edition="Ph.Eur. 11.0", valid_from=date(2023, 1, 1),
        monograph_name="Lisinoprilum dihydricum", page="3812",
        source_note=_MOCK_NOTE,
    ),
]


class MockMonographRepository:
    """
    In-memory mock implementation of MonographRepository.

    Uses explicitly labelled synthetic records only.
    Never invents data beyond what is listed in _MOCK_RECORDS.
    """

    def get_current_edition(
        self,
        standard: str,
        substance_name: str,
        as_of,  # date | None
    ) -> MonographRecord | None:
        if as_of is None:
            # Cannot determine currency without a submission date — treat as not found
            return None
        candidates = [
            r for r in _MOCK_RECORDS
            if r.standard.upper() == standard.upper()
            and r.substance_name.lower() == substance_name.lower()
            and r.valid_from <= as_of
        ]
        if not candidates:
            return None
        # Most recent edition that was valid on or before as_of
        return max(candidates, key=lambda r: r.valid_from)


# ── IPRP criterion mapping (Phase 6) ─────────────────────────────────────────

# IPRP QWGG Guidance, Section S.5, page 18.  Eight criteria:
#   S5-QAR-01 through S5-QAR-04 — Quality Assessment Report sub-items (a)–(d)
#   S5-AS-05  through S5-AS-08  — Assessment-specific criteria
_CRITERION_LABELS: dict[str, str] = {
    "S5-QAR-01": "Primary reference standard — lot number and standard type (sub-item a)",
    "S5-QAR-02": "CoA and overlaid IR spectra submitted (sub-item b)",
    "S5-QAR-03": "Secondary/working standard qualified against primary (sub-item c)",
    "S5-QAR-04": "Source of reference standards for identification, purity, potency (sub-item d)",
    "S5-AS-05":  "Compendial standard — edition current at submission date",
    "S5-AS-06":  "In-house primary standard — full characterisation and purity assignment",
    "S5-AS-07":  "Impurity reference standards — characterisation and assigned purity",
    "S5-AS-08":  "Ph. Eur. reference standard — used for content, not identity only",
}

_COMPENDIAL_TYPES = {
    ReferenceStandardType.COMPENDIAL,
    ReferenceStandardType.COMPENDIAL_PRIMARY,
}
_INHOUSE_TYPES = {
    ReferenceStandardType.IN_HOUSE,
    ReferenceStandardType.IN_HOUSE_PRIMARY,
}


def _derive_criterion_id(claim: S5Claim) -> str:
    """
    Return the single most specific IPRP criterion this claim maps to.

    Priority order (most specific first):
      S5-AS-08 — Ph. Eur. standard declared
      S5-AS-07 — impurity standards declared
      S5-AS-06 — in-house primary standard
      S5-AS-05 — compendial standard
      S5-QAR-01 — default anchor (sub-item a is always required)
    """
    _std_norm = claim.standard.upper().replace(" ", "").replace(".", "")
    if _std_norm in {"PHEUR", "PE"}:
        return "S5-AS-08"
    if claim.impurity_standards is not None:
        return "S5-AS-07"
    if claim.standard_type in _INHOUSE_TYPES:
        return "S5-AS-06"
    if claim.standard_type in _COMPENDIAL_TYPES:
        return "S5-AS-05"
    return "S5-QAR-01"


def _derive_applicability_status(claim: S5Claim, criterion_id: str) -> str:
    """
    Determine whether the given criterion is applicable to this claim.

    Values:
      APPLICABLE      — criterion clearly applies given the claim's declared fields
      NOT_APPLICABLE  — criterion explicitly does not apply (e.g. no impurity standards)
      NOT_PROVIDED    — cannot determine applicability; required fields are absent
      UNCLEAR         — fields are present but contradictory

    Rules:
      S5-QAR-01..04  — always APPLICABLE (all primary standard submissions require them)
      S5-AS-05       — APPLICABLE if standard_type is compendial; NOT_PROVIDED if None
      S5-AS-06       — APPLICABLE if standard_type is in-house; NOT_APPLICABLE if compendial
      S5-AS-07       — APPLICABLE if impurity_standards list declared; NOT_APPLICABLE if None
      S5-AS-08       — APPLICABLE if standard is Ph.Eur.; NOT_APPLICABLE otherwise
    """
    if criterion_id in ("S5-QAR-01", "S5-QAR-02", "S5-QAR-03", "S5-QAR-04"):
        return "APPLICABLE"

    if criterion_id == "S5-AS-05":
        if claim.standard_type is None:
            return "NOT_PROVIDED"
        if claim.standard_type in _COMPENDIAL_TYPES:
            return "APPLICABLE"
        return "NOT_APPLICABLE"

    if criterion_id == "S5-AS-06":
        if claim.standard_type is None:
            return "NOT_PROVIDED"
        if claim.standard_type in _INHOUSE_TYPES:
            return "APPLICABLE"
        return "NOT_APPLICABLE"

    if criterion_id == "S5-AS-07":
        if claim.impurity_standards is None:
            return "NOT_APPLICABLE"
        return "APPLICABLE"

    if criterion_id == "S5-AS-08":
        _std_norm = claim.standard.upper().replace(" ", "").replace(".", "")
        if _std_norm in {"PHEUR", "PE"}:
            return "APPLICABLE"
        return "NOT_APPLICABLE"

    return "UNCLEAR"


# ── IPRP completeness checker ─────────────────────────────────────────────────

def _check_completeness(claim: S5Claim) -> list[str]:
    """
    Check the claim against the IPRP QWGG S.5 checklist.

    Returns a list of human-readable flag strings — one per missing required
    field.  An empty list means the submission is structurally complete for S.5.

    Sub-item mapping:
      (a) lot_number + standard_type  [+ in-house characterisation if in-house]
      (b) coa_submitted + ir_spectra_submitted
      (c) working_std_qualified_against_primary
      (d) reference_standard_source_detail
    """
    flags: list[str] = []

    # Sub-item (a): lot/batch number required for all primary standards
    if not claim.lot_number:
        flags.append(
            "sub-item (a): lot/batch number of the primary reference standard not provided"
        )

    # Sub-item (a): standard type (compendial vs in-house) must be declared
    if claim.standard_type is None:
        flags.append(
            "sub-item (a): standard type (compendial / in-house) not declared"
        )

    # Sub-item (a): in-house primary — full characterisation required
    if claim.standard_type == ReferenceStandardType.IN_HOUSE:
        if not claim.inhouse_characterisation_methods:
            flags.append(
                "sub-item (a): in-house primary standard — characterisation methods "
                "(IR, UV, NMR, MS) not provided"
            )
        elif not any(
            m.strip().upper() == "IR" for m in claim.inhouse_characterisation_methods
        ):
            # IPRP S.5 bullet (c) specifically calls out IR as a required method.
            # A non-empty list that does not include IR is insufficient.
            flags.append(
                "sub-item (a): in-house primary standard — IR spectroscopy not listed "
                "among characterisation methods; IR is explicitly required by IPRP S.5"
            )
        if claim.inhouse_purity_assigned is None:
            flags.append(
                "sub-item (a): in-house primary standard — purity assignment "
                "(mass balance or absolute purity) not stated"
            )
        if claim.inhouse_coa_submitted is None:
            flags.append(
                "sub-item (a): in-house primary standard — CoA submission status not stated"
            )

    # Sub-item (b): CoA and overlaid IR spectra
    if claim.coa_submitted is None:
        flags.append(
            "sub-item (b): certificate of analysis (CoA) submission not stated"
        )
    if claim.ir_spectra_submitted is None:
        flags.append(
            "sub-item (b): overlaid IR spectra submission not stated"
        )

    # Sub-item (c): working standard traceability
    if claim.working_std_qualified_against_primary is None:
        flags.append(
            "sub-item (c): secondary/working standard qualification against "
            "compendial or primary reference standard not stated"
        )

    # Sub-item (d): source of standards used for testing
    if not claim.reference_standard_source_detail:
        flags.append(
            "sub-item (d): source of reference standards used for identification, "
            "purity, and potency testing not provided"
        )

    # Sub-item (d) — Ph. Eur. specific: if a Ph. Eur. reference standard is used
    # for quantitative analysis, it must be for content, not identity only.
    # IPRP assessment point (i); Ph. Eur. 5.12 §4-2-3.
    # Normalise the standard name to catch 'Ph. Eur.', 'Ph.Eur.', 'PhEur', etc.
    _std_norm = claim.standard.upper().replace(" ", "").replace(".", "")
    if _std_norm in {"PHEUR", "PE"}:
        if claim.ph_eur_used_for_content is None:
            flags.append(
                "sub-item (d): Ph. Eur. reference standard declared — must state whether "
                "the standard is used for content (quantitative analysis) rather than "
                "identity only (IPRP assessment point i; Ph. Eur. 5.12 §4-2-3)"
            )

    # Impurity standards — IPRP assessment point (iv):
    # "Impurity standard (characterisation, purity), if applicable."
    # Only checked when the applicant has declared impurity standards (list is not None).
    # None = not applicable / not declared; empty list = declared but empty (also flagged).
    if claim.impurity_standards is not None:
        if len(claim.impurity_standards) == 0:
            flags.append(
                "impurity standards: list declared but contains no entries"
            )
        for imp in claim.impurity_standards:
            # Each impurity standard must have an assigned purity value (Phase 2: purity_percent)
            if imp.purity_percent is None:
                flags.append(
                    f"impurity standard '{imp.official_name}': purity not assigned "
                    "(IPRP assessment point iv — characterisation and purity required)"
                )
            # Each impurity standard must have at least one characterisation method
            if not imp.characterisation_methods:
                flags.append(
                    f"impurity standard '{imp.official_name}': characterisation methods "
                    "(e.g. IR, NMR, MS) not provided "
                    "(IPRP assessment point iv)"
                )

    return flags


# ── Evidence sufficiency derivation (Phase 4) ─────────────────────────────────

def _derive_evidence_sufficiency(
    verdict: str,
    completeness_flags: list[str],
    evidence_tier: "str | None" = None,
) -> str:
    """
    Map verdict + completeness_flags + evidence_tier to an evidence_sufficiency
    category.  Phase 4 extends the original two-parameter signature with an
    optional ``evidence_tier`` argument; all existing call sites that omit it
    continue to work unchanged (backward-compatible default = None).

    Decision table (evaluated in priority order)
    --------------------------------------------
    1. CONFLICTING
       Triggered when ``evidence_tier == "CONFLICTING"``.  Reserved for the
       case where two independent retrieval sources (e.g. CrossRef + an ingested
       document) return contradictory edition data for the same substance.
       No verdict check is performed — the conflict itself is the signal.

    2. SUPPORTED
       ``verdict == "COMPLIANT"``
       AND ``completeness_flags`` is empty
       AND ``evidence_tier`` is NOT a low-authority tier
       (i.e. not TIER_2_GUIDANCE, TIER_3_DISCOVERY_ONLY, or NEEDS_REVIEW).
       All IPRP sub-items are present, the edition is current, and the source
       is authoritative (Tier 1 or repository-confirmed).

    3. PARTIAL — lower-authority COMPLIANT
       ``verdict == "COMPLIANT"`` AND no flags BUT ``evidence_tier`` is
       TIER_2_GUIDANCE or TIER_3_DISCOVERY_ONLY (ingested-document or
       discovery-only evidence).  Edition claim appears consistent with the
       ingested text but cannot be promoted to SUPPORTED without an
       authoritative Tier-1 confirmation.

    4. PARTIAL — resolved with structural gaps, or NON_COMPLIANT
       ``verdict in ("COMPLIANT", "NON_COMPLIANT")`` (with any flag count,
       or NON_COMPLIANT with no flags).  Edition check resolved but either
       structural IPRP gaps remain, or an edition mismatch was detected.

    5. INSUFFICIENT
       ``verdict == "NEEDS_REVIEW"`` AND ``completeness_flags`` is non-empty.
       Edition data is unavailable AND structural gaps are present — the
       dossier cannot be assessed without additional information.

    6. NOT_VERIFIED  (default)
       ``verdict == "NEEDS_REVIEW"`` AND ``completeness_flags`` is empty.
       Edition data gap only (repository has no record for this substance).
       Claim is otherwise structurally complete — escalate to pharmacopoeial
       manual check.

    Evidence tier constants (from retrieval.py)
    -------------------------------------------
    TIER_1_EXISTENCE_CONFIRMED  — CrossRef DOI confirmed; content not read.
    TIER_1_CONTENT_VERIFIED     — Human verified against primary source.
    TIER_2_GUIDANCE             — Ingested regulatory guidance / mapping doc.
    TIER_3_DISCOVERY_ONLY       — General web discovery; never authoritative.
    NEEDS_REVIEW                — No tier assigned yet.
    CONFLICTING                 — Sentinel: two sources gave contradictory data.
    """
    # Rule 1 — CONFLICTING sentinel takes absolute priority
    if evidence_tier == "CONFLICTING":
        return "CONFLICTING"

    # Low-authority tier constants (Tier 2 / Tier 3 / unresolved)
    _LOW_AUTHORITY_TIERS = {"TIER_2_GUIDANCE", "TIER_3_DISCOVERY_ONLY", "NEEDS_REVIEW"}

    # Rule 2 — SUPPORTED: authoritative COMPLIANT with no structural gaps
    if (
        verdict == "COMPLIANT"
        and not completeness_flags
        and evidence_tier not in _LOW_AUTHORITY_TIERS
    ):
        return "SUPPORTED"

    # Rule 3 — PARTIAL: ingested-document COMPLIANT (lower authority)
    if (
        verdict == "COMPLIANT"
        and not completeness_flags
        and evidence_tier in _LOW_AUTHORITY_TIERS
    ):
        return "PARTIAL"

    # Rule 4 — PARTIAL: edition resolved with gaps, or NON_COMPLIANT
    if verdict in ("COMPLIANT", "NON_COMPLIANT"):
        return "PARTIAL"

    # Rule 5 — INSUFFICIENT: unresolvable with structural gaps
    if verdict == "NEEDS_REVIEW" and completeness_flags:
        return "INSUFFICIENT"

    # Rule 6 — NOT_VERIFIED: repository data gap, claim otherwise complete
    return "NOT_VERIFIED"


# ── Agent logic ───────────────────────────────────────────────────────────────

def check_s5_claim(
    claim: S5Claim,
    repository: MonographRepository,
    retrieval_enabled: bool = False,
    ollama_enabled: bool = False,
) -> S5Finding:
    """
    Validate one S.5 sponsor claim against the IPRP checklist and the
    monograph repository.

    Steps:
      1. Run completeness check (all IPRP sub-items a–d).
      2. Look up the current edition in the repository.
      3. Compare claimed vs current edition → verdict.
      4. Derive evidence_sufficiency from verdict + completeness_flags (Phase 4).
      5. Optionally populate web-retrieval provenance fields (retrieval_enabled).
      6. Optionally call Ollama for LLM reasoning commentary (ollama_enabled, Phase 5).

    Returns an S5Finding with:
      COMPLIANT     if claimed edition == current edition at submission date.
      NON_COMPLIANT if a current edition exists and differs from claimed.
      NEEDS_REVIEW  if no record is available; no verdict is made.

    completeness_flags is populated regardless of verdict — a claim can be
    COMPLIANT on the edition check but still have missing IPRP sub-items.

    retrieval_enabled=False (default) — no outbound network requests.
    ollama_enabled=False (default) — no Ollama call; model_review remains None.
    """
    completeness_flags = _check_completeness(claim)

    # ── Phase 3 / Phase 4: pre-check ingested documents ─────────────────────
    #
    # Phase 4 RAG enhancement: query the KB source types (iprp_guidance,
    # pharmacopoeia, v2_mapping, score_report) SEPARATELY from the applicant
    # dossier (applicant_dossier) so they are never conflated.
    #
    # kb_hits   — regulatory evidence from the ingested knowledge base.
    # dossier_hits — applicant-supplied evidence from the uploaded dossier.
    #
    # Both lists are passed down to build_assessment_report() so each
    # S5CriterionResult can carry real supporting_documents references.
    #
    # Falls through silently to the repository lookup when the store is empty.
    _KB_SOURCE_TYPES = [
        "iprp_guidance", "pharmacopoeia", "v2_mapping", "score_report",
    ]
    _DOSSIER_SOURCE_TYPES = ["applicant_dossier"]

    kb_hits: list = []
    dossier_hits: list = []
    try:
        from retrieval import query_ingested_documents  # noqa: PLC0415
        kb_hits = query_ingested_documents(
            standard=claim.standard,
            substance_name=claim.substance_name,
            source_types=_KB_SOURCE_TYPES,
        )
        dossier_hits = query_ingested_documents(
            standard=claim.standard,
            substance_name=claim.substance_name,
            source_types=_DOSSIER_SOURCE_TYPES,
        )
    except Exception as _exc:  # noqa: BLE001
        logger.warning(
            "Phase 4 RAG pre-check: query_ingested_documents raised %s; "
            "falling through to repository lookup.",
            _exc,
        )

    # Combine for the early-return path (any ingested evidence triggers it)
    ingested_hits = kb_hits + dossier_hits

    if ingested_hits:
        # Separate summaries keep KB evidence and applicant evidence traceable.
        def _hit_summary(hits: list, label: str) -> str:
            if not hits:
                return f"{label}: none"
            lines = "; ".join(
                f"[{h.source_type.value}:{h.section_id}] {h.raw_text[:100].strip()}"
                for h in hits[:4]
            )
            return f"{label} ({len(hits)} section(s)): {lines}"

        _kb_summary = _hit_summary(kb_hits, "KB evidence")
        _dossier_summary = _hit_summary(dossier_hits, "Applicant dossier")

        _ingested_verdict = "NEEDS_REVIEW"  # ingested text is not authoritative
        _ingested_criterion_id = _derive_criterion_id(claim)
        _ingested_applicability = _derive_applicability_status(claim, _ingested_criterion_id)

        from models import S5Finding as _S5Finding
        _finding = _S5Finding(
            substance_name=claim.substance_name,
            standard_claimed=claim.standard,
            edition_claimed=claim.edition_claimed,
            monograph_name=None,
            edition_current=None,
            evidence=(
                f"RAG retrieval: {len(kb_hits)} KB section(s) and "
                f"{len(dossier_hits)} dossier section(s) found for "
                f"{claim.standard} / {claim.substance_name}. "
                f"{_kb_summary}. {_dossier_summary}."
            ),
            citation=None,
            verdict=_ingested_verdict,
            verdict_reason=(
                "Evidence sourced from ingested documents only. "
                "content_verified=False — a human reviewer must consult the "
                "primary pharmacopoeial source before a compliance verdict can be issued."
            ),
            source_note=(
                f"Phase 4 RAG retrieval — "
                f"KB: {len(kb_hits)} hit(s) across "
                + ", ".join(sorted({h.source_type.value for h in kb_hits}) or ["none"])
                + f"; Dossier: {len(dossier_hits)} hit(s)"
            ),
            completeness_flags=completeness_flags,
            evidence_sufficiency=_derive_evidence_sufficiency(
                _ingested_verdict, completeness_flags,
                evidence_tier="TIER_2_GUIDANCE" if kb_hits else "TIER_3_APPLICANT",
            ),
            criterion_id=_ingested_criterion_id,
            applicability_status=_ingested_applicability,
            evidence_tier="TIER_2_GUIDANCE" if kb_hits else "TIER_3_APPLICANT",
            content_verified=False,
        )
        # NOTE: build_assessment_report() is NOT called here — it is called by
        # POST /s5/assess after review_s5_finding().  The kb_hits and dossier_hits
        # are stored on the finding via notes so they reach build_assessment_report().
        # They are encoded as a compact JSON string in finding.source_note to avoid
        # adding a new field to S5Finding (which would require a model change).
        # build_assessment_report() decodes them from _kb_hits / _dossier_hits kwargs
        # passed by POST /s5/assess (see main.py Phase 4 wiring).
        #
        # For now, store hit refs in source_note for traceability; the report
        # builder receives them via the new optional parameters added in Fix 3.
        return _finding
    # End Phase 3 / Phase 4 pre-check — fall through to repository lookup below.

    # Phase 6: derive criterion and applicability once, shared across all branches
    _criterion_id = _derive_criterion_id(claim)
    _applicability_status = _derive_applicability_status(claim, _criterion_id)

    # Guard: missing edition_claimed means we cannot compare → NEEDS_REVIEW immediately.
    # Prevents None != "BP 2024" being treated as NON_COMPLIANT (incorrect — the applicant
    # simply hasn't stated their edition yet).
    if claim.edition_claimed is None:
        completeness_flags = _check_completeness(claim)
        return S5Finding(
            substance_name=claim.substance_name,
            standard_claimed=claim.standard,
            edition_claimed=None,
            monograph_name=None,
            edition_current=None,
            evidence=(
                f"Edition claimed was not stated for {claim.standard} / "
                f"{claim.substance_name}. Cannot assess compliance."
            ),
            citation=None,
            verdict="NEEDS_REVIEW",
            verdict_reason="Edition claimed not stated — unable to perform edition comparison.",
            source_note="[mock] Edition check skipped: edition_claimed is None.",
            completeness_flags=completeness_flags,
            evidence_sufficiency="INSUFFICIENT",
            criterion_id=_criterion_id,
            applicability_status=_applicability_status,
        )

    record = repository.get_current_edition(
        standard=claim.standard,
        substance_name=claim.substance_name,
        as_of=claim.submission_date,
    )

    # ── Build the core finding ────────────────────────────────────────────────

    if record is None:
        _verdict = "NEEDS_REVIEW"
        finding = S5Finding(
            substance_name=claim.substance_name,
            standard_claimed=claim.standard,
            edition_claimed=claim.edition_claimed,
            monograph_name=None,
            edition_current=None,
            evidence=(
                f"No monograph record found for {claim.standard} / "
                f"{claim.substance_name} as of {claim.submission_date}."
            ),
            citation=None,
            verdict=_verdict,
            verdict_reason=(
                "Reference information unavailable. "
                "Manual pharmacopoeial check required before a compliance verdict can be issued."
            ),
            source_note="No record available in the current repository.",
            completeness_flags=completeness_flags,
            evidence_sufficiency=_derive_evidence_sufficiency(
                _verdict, completeness_flags, evidence_tier=None
            ),
            criterion_id=_criterion_id,
            applicability_status=_applicability_status,
        )

    else:
        citation = (
            f"{record.monograph_name}, {record.edition}"
            + (f", p. {record.page}" if record.page else "")
        )

        if (claim.edition_claimed or '').strip().upper() == record.edition.strip().upper():
            _verdict = "COMPLIANT"
            finding = S5Finding(
                substance_name=claim.substance_name,
                standard_claimed=claim.standard,
                edition_claimed=claim.edition_claimed,
                monograph_name=record.monograph_name,
                edition_current=record.edition,
                evidence=(
                    f"Sponsor claims {claim.edition_claimed}. "
                    f"Current edition at submission date ({claim.submission_date}) "
                    f"is {record.edition}. Editions match."
                ),
                citation=citation,
                verdict=_verdict,
                verdict_reason="Claimed edition matches the current edition at submission date.",
                source_note=record.source_note,
                completeness_flags=completeness_flags,
                evidence_sufficiency=_derive_evidence_sufficiency(
                    _verdict, completeness_flags,
                    evidence_tier="TIER_1_EXISTENCE_CONFIRMED",
                ),
                criterion_id=_criterion_id,
                applicability_status=_applicability_status,
            )
        else:
            _verdict = "NON_COMPLIANT"
            finding = S5Finding(
                substance_name=claim.substance_name,
                standard_claimed=claim.standard,
                edition_claimed=claim.edition_claimed,
                monograph_name=record.monograph_name,
                edition_current=record.edition,
                evidence=(
                    f"Sponsor claims {claim.edition_claimed}. "
                    f"Current edition at submission date ({claim.submission_date}) "
                    f"is {record.edition}. Editions differ."
                ),
                citation=citation,
                verdict=_verdict,
                verdict_reason=(
                    f"Claimed edition ({claim.edition_claimed}) is not the current edition "
                    f"({record.edition}) at submission date ({claim.submission_date})."
                ),
                source_note=record.source_note,
                completeness_flags=completeness_flags,
                evidence_sufficiency=_derive_evidence_sufficiency(
                    _verdict, completeness_flags,
                    evidence_tier="TIER_1_EXISTENCE_CONFIRMED",
                ),
                criterion_id=_criterion_id,
                applicability_status=_applicability_status,
            )

    # ── Optional web-retrieval provenance (Phase 3 / Fix 4) ──────────────────
    # Runs only when retrieval_enabled=True.  Never raises; never overrides
    # the verdict produced above.  Populates the five provenance fields.

    if retrieval_enabled:
        web_repo = _WebMonographRepository()
        retrieved = web_repo.get(claim.substance_name)
        finding = finding.model_copy(update={
            "source_url":        retrieved.doi_url,
            "retrieved_at":      retrieved.retrieved_at,
            "evidence_tier":     retrieved.evidence_tier,
            "content_verified":  retrieved.content_verified,
            "raw_excerpt":       retrieved.raw_excerpt,
        })

    # ── Optional Ollama LLM reasoning (Phase 5) ───────────────────────────────
    # Runs only when ollama_enabled=True.  Never raises; never overrides verdict
    # or evidence_sufficiency.  Populates model_review on the returned S5Finding,
    # or leaves it None if Ollama is unreachable or returns invalid output.

    if ollama_enabled:
        try:
            from ollama_reviewer import (
                check_ollama_available,
                pick_model,
                run_ollama_review,
            )
            reachable, available_models = check_ollama_available()
            if not reachable:
                logger.info(
                    "ollama_enabled=True but Ollama is not reachable at %s. "
                    "model_review will be None.",
                    "http://localhost:11434",
                )
            else:
                model = pick_model(available_models)
                if model is None:
                    logger.warning(
                        "Ollama is running but no preferred model is available. "
                        "Available models: %s. model_review will be None.",
                        available_models,
                    )
                else:
                    review = run_ollama_review(claim, finding, model, kb_hits=kb_hits, dossier_hits=dossier_hits)
                    if review is not None:
                        finding = finding.model_copy(update={"model_review": review})
        except Exception as exc:  # noqa: BLE001
            # Defensive catch — Ollama errors must never crash the assessment.
            logger.error(
                "Unexpected error in Ollama integration: %s. "
                "model_review will be None.",
                exc,
            )

    return finding


# ── Phase 9: IPRP-aligned structured assessment report builder ────────────────

def build_assessment_report(  # noqa: F821
    claim: S5Claim,
    finding: S5Finding,
    kb_hits: "list | None" = None,
    dossier_hits: "list | None" = None,
) -> "S5AssessmentReport":
    """
    Build an S5AssessmentReport containing exactly 8 S5CriterionResult items
    from the existing S5Claim and QA-stamped S5Finding.

    This function is PURELY COMPOSITIONAL — it re-uses data already present
    in the claim and finding.  It does NOT:
      - Make any network requests.
      - Call the monograph repository.
      - Set or modify verdict, qa_status, or evidence_sufficiency.
      - Fabricate pharmaceutical values not present in the claim.

    When a required value is None / absent, the criterion's missing_info list
    is populated and evidence_verification_status is set to MISSING.

    IPRP criteria order:
      S5-QAR-01 — Description and sources
      S5-QAR-02 — Primary RS type and batch
      S5-QAR-03 — In-house primary characterisation (applicability depends on standard_type)
      S5-QAR-04 — Secondary/working standard
      S5-AS-01  — Sources and intended uses
      S5-AS-02  — Primary standard preparation and purity
      S5-AS-03  — Secondary standard purity and batch
      S5-AS-04  — Impurity standards (applicability depends on impurity_standards)
    """
    from datetime import datetime, timezone
    from models import (
        S5CriterionResult,
        S5QAReviewSummary,
        S5AssessmentReport,
    )

    _now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Phase 4 RAG: build supporting-document index ─────────────────────────
    # Map each ExtractionResult hit to a compact "doc_id:section_id" reference.
    # _kb_refs   — from regulatory KB (iprp_guidance, pharmacopoeia, etc.)
    # _dos_refs  — from applicant dossier
    # Both are keyed by lowercase keywords so criteria can look up relevant refs.
    _kb_refs: list[str] = [
        f"{h.doc_id}:{h.section_id}"
        for h in (kb_hits or [])
    ]
    _dos_refs: list[str] = [
        f"{h.doc_id}:{h.section_id}"
        for h in (dossier_hits or [])
    ]

    def _kb_texts() -> list[str]:
        """Return raw_text from all KB hits (for keyword matching)."""
        return [h.raw_text.lower() for h in (kb_hits or [])]

    def _dos_texts() -> list[str]:
        """Return raw_text from all dossier hits (for keyword matching)."""
        return [h.raw_text.lower() for h in (dossier_hits or [])]

    def _refs_for_criterion(keywords: list[str]) -> tuple[list[str], str]:
        """
        Return (supporting_docs, evidence_verification_status) for a criterion.

        supporting_docs: KB refs whose raw_text contains any of the keywords,
                         plus all dossier refs (always included when present —
                         the applicant dossier is always relevant to the criterion
                         but never counts as independent verification).
        status: "SUPPORTED" when at least one KB ref matches a keyword,
                "NOT_VERIFIED" otherwise.
        """
        matched_kb: list[str] = []
        kb_text_list = _kb_texts()
        for i, text in enumerate(kb_text_list):
            if any(kw.lower() in text for kw in keywords):
                matched_kb.append(_kb_refs[i])
        docs = matched_kb + _dos_refs
        status = "SUPPORTED" if matched_kb else "NOT_VERIFIED"
        return docs, status

    _inhouse_types = {"in-house", "in_house_primary"}

    def _is_inhouse(claim: S5Claim) -> bool:
        return (
            claim.standard_type is not None
            and claim.standard_type.value in _inhouse_types
        )

    criteria: list[S5CriterionResult] = []

    # ── S5-QAR-01: Description and sources ───────────────────────────────────
    _qar01_info: dict = {
        "standard": claim.standard,
        "standard_type": claim.standard_type.value if claim.standard_type else None,
        "reference_standard_source_detail": claim.reference_standard_source_detail,
    }
    _qar01_missing = []
    _qar01_questions = []
    if not claim.reference_standard_source_detail:
        _qar01_missing.append(
            "reference_standard_source_detail not provided — "
            "IPRP sub-item (d): source of RS for identification, purity and potency testing required"
        )
        _qar01_questions.append(
            "State the source of all reference standards used for identification, purity and potency testing."
        )
    if claim.standard_type is None:
        _qar01_missing.append(
            "standard_type not declared (compendial / in-house / other)"
        )
        _qar01_questions.append(
            "Declare whether the primary reference standard is compendial or in-house."
        )
    _qar01_docs, _qar01_ev = _refs_for_criterion(
        ["reference standard", "source", "description", "s.5", "3.2.s.5"]
    )
    criteria.append(S5CriterionResult(
        criterion_id="S5-QAR-01",
        criterion_title="Description and sources of reference standards or materials",
        applicability="APPLICABLE",
        extracted_info=_qar01_info,
        regulatory_guidance="IPRP QWGG S.5 sub-item (d); Ph. Eur. 5.12 §3",
        assessment_finding=(
            "RS standard and type declared; source detail "
            + ("stated." if claim.reference_standard_source_detail else "MISSING.")
        ),
        missing_info=_qar01_missing,
        supporting_documents=_qar01_docs,
        evidence_verification_status="MISSING" if _qar01_missing else _qar01_ev,
        assessor_questions=_qar01_questions,
    ))

    # ── S5-QAR-02: Primary RS type and batch number ───────────────────────────
    _qar02_info: dict = {
        "standard_type": claim.standard_type.value if claim.standard_type else None,
        "lot_number": claim.lot_number,
        "edition_claimed": claim.edition_claimed,
        "edition_current": finding.edition_current,
        "verdict": finding.verdict,
    }
    _qar02_missing = []
    _qar02_questions = []
    if not claim.lot_number:
        _qar02_missing.append(
            "lot_number not provided — "
            "IPRP sub-item (a): batch/lot number of primary RS required"
        )
        _qar02_questions.append(
            "Provide the lot/batch number of the primary reference standard."
        )
    if finding.verdict == "NON_COMPLIANT":
        _qar02_missing.append(
            f"Edition mismatch: claimed {claim.edition_claimed}, "
            f"current {finding.edition_current} at submission date {claim.submission_date}"
        )
        _qar02_questions.append(
            f"Confirm whether {claim.edition_claimed} was the current edition "
            f"at submission date {claim.submission_date}. "
            f"Repository shows {finding.edition_current} as current."
        )
    _qar02_docs, _qar02_ev = _refs_for_criterion(
        ["batch", "lot", "primary standard", "compendial", "edition", "pharmacopoeia"]
    )
    criteria.append(S5CriterionResult(
        criterion_id="S5-QAR-02",
        criterion_title="Primary reference standard type and batch number",
        applicability="APPLICABLE",
        extracted_info=_qar02_info,
        regulatory_guidance="IPRP QWGG S.5 sub-item (a)",
        assessment_finding=(
            f"Standard type: {claim.standard_type.value if claim.standard_type else 'NOT DECLARED'}. "
            f"Lot: {claim.lot_number or 'NOT PROVIDED'}. "
            f"Edition verdict: {finding.verdict}."
        ),
        missing_info=_qar02_missing,
        supporting_documents=_qar02_docs,
        evidence_verification_status="MISSING" if _qar02_missing else _qar02_ev,
        assessor_questions=_qar02_questions,
    ))

    # ── S5-QAR-03: In-house primary characterisation ──────────────────────────
    _qar03_docs, _qar03_ev = _refs_for_criterion(
        ['in-house', 'characterisation', 'primary standard', 'purity', 'certificate', 'coa']
    )
    if _is_inhouse(claim):
        _qar03_info: dict = {
            "inhouse_characterisation_methods": claim.inhouse_characterisation_methods,
            "inhouse_purity_assigned": claim.inhouse_purity_assigned,
            "inhouse_coa_submitted": claim.inhouse_coa_submitted,
        }
        _qar03_missing = []
        _qar03_questions = []
        if not claim.inhouse_characterisation_methods:
            _qar03_missing.append(
                "inhouse_characterisation_methods not provided — "
                "IPRP: in-house primary RS must state characterisation methods (IR, UV, NMR, MS)"
            )
            _qar03_questions.append(
                "Provide the characterisation methods used for the in-house primary RS (e.g. IR, UV, NMR, MS)."
            )
        elif not any(m.strip().upper() == "IR" for m in claim.inhouse_characterisation_methods):
            _qar03_missing.append(
                "IR spectroscopy not listed among characterisation methods — "
                "IPRP S.5 explicitly requires IR for in-house primary standards"
            )
            _qar03_questions.append(
                "Confirm whether IR spectroscopy was performed on the in-house primary RS."
            )
        if claim.inhouse_purity_assigned is None:
            _qar03_missing.append(
                "inhouse_purity_assigned not stated — "
                "IPRP: state whether purity was assigned by mass balance or absolute purity"
            )
            _qar03_questions.append(
                "State whether purity has been assigned and by which method (mass balance or absolute purity)."
            )
        if claim.inhouse_coa_submitted is None:
            _qar03_missing.append(
                "inhouse_coa_submitted not stated — "
                "IPRP: CoA submission required for in-house primary RS"
            )
            _qar03_questions.append(
                "Confirm whether a CoA has been submitted for the in-house primary RS."
            )
        criteria.append(S5CriterionResult(
            criterion_id="S5-QAR-03",
            criterion_title="In-house primary RS characterisation, CoA and purity determination",
            applicability="APPLICABLE",
            extracted_info=_qar03_info,
            regulatory_guidance="IPRP QWGG S.5 sub-item (a) in-house branch; Ph. Eur. 5.12 §4-1",
            assessment_finding=(
                "In-house primary RS declared. "
                + (
                    f"Characterisation methods: {', '.join(claim.inhouse_characterisation_methods)}. "
                    if claim.inhouse_characterisation_methods else "Characterisation methods: NOT PROVIDED. "
                )
                + f"Purity assigned: {claim.inhouse_purity_assigned}. "
                + f"CoA submitted: {claim.inhouse_coa_submitted}."
            ),
            missing_info=_qar03_missing,
            supporting_documents=_qar03_docs,
            evidence_verification_status="MISSING" if _qar03_missing else "NOT_VERIFIED",
            assessor_questions=_qar03_questions,
        ))
    else:
        criteria.append(S5CriterionResult(
            criterion_id="S5-QAR-03",
            criterion_title="In-house primary RS characterisation, CoA and purity determination",
            applicability="NOT_APPLICABLE",
            extracted_info=None,
            regulatory_guidance="IPRP QWGG S.5 sub-item (a) in-house branch; Ph. Eur. 5.12 §4-1",
            assessment_finding="Not applicable — compendial or non-in-house standard declared.",
            missing_info=[],
            supporting_documents=_qar03_docs,
            evidence_verification_status="NOT_APPLICABLE",
            assessor_questions=[],
        ))

    # ── S5-QAR-04: Secondary / working standard ───────────────────────────────
    _qar04_info: dict = {
        "working_standard_lot": claim.working_standard_lot,
        "working_standard_source": claim.working_standard_source,
        "working_std_qualified_against_primary": claim.working_std_qualified_against_primary,
        "working_standard_assay": claim.working_standard_assay,
    }
    _qar04_missing = []
    _qar04_questions = []
    if claim.working_std_qualified_against_primary is None:
        _qar04_missing.append(
            "working_std_qualified_against_primary not stated — "
            "IPRP sub-item (c): state whether secondary standard is standardised against primary"
        )
        _qar04_questions.append(
            "State whether the working/secondary standard has been standardised against "
            "the compendial or primary reference standard."
        )
    if claim.working_standard_assay is None:
        _qar04_missing.append(
            "working_standard_assay not provided — "
            "Ph. Eur. 5.12 §4-5: assigned purity of the working standard required"
        )
        _qar04_questions.append(
            "Provide the assigned purity value of the working/secondary standard "
            "(e.g. 100.4% on anhydrous basis)."
        )
    _qar04_docs, _qar04_ev = _refs_for_criterion(
        ['working standard', 'secondary standard', 'purity', 'qualification', 'standardised']
    )
    criteria.append(S5CriterionResult(
        criterion_id="S5-QAR-04",
        criterion_title="Secondary/working standard standardisation against compendial or primary RS",
        applicability="APPLICABLE",
        extracted_info=_qar04_info,
        regulatory_guidance="IPRP QWGG S.5 sub-item (c); Ph. Eur. 5.12 §4-5",
        assessment_finding=(
            f"Working std lot: {claim.working_standard_lot or 'NOT PROVIDED'}. "
            f"Source: {claim.working_standard_source or 'NOT PROVIDED'}. "
            f"Qualified against primary: {claim.working_std_qualified_against_primary}. "
            f"Assigned purity: {f'{claim.working_standard_assay}%' if claim.working_standard_assay is not None else 'NOT PROVIDED'}."
        ),
        missing_info=_qar04_missing,
        supporting_documents=_qar04_docs,
        evidence_verification_status="MISSING" if _qar04_missing else _qar04_ev,
        assessor_questions=_qar04_questions,
    ))

    # ── S5-AS-01: Sources and intended uses ───────────────────────────────────
    _as01_info: dict = {
        "reference_standard_source_detail": claim.reference_standard_source_detail,
        "intended_use": claim.intended_use,
    }
    _as01_missing = []
    _as01_questions = []
    if not claim.reference_standard_source_detail:
        _as01_missing.append(
            "reference_standard_source_detail not provided — source of RS required"
        )
    if claim.intended_use is None or len(claim.intended_use) == 0:
        _as01_missing.append(
            "intended_use not declared — IPRP assessment point (i): "
            "state intended uses (e.g. assay, related substances, identification)"
        )
        _as01_questions.append(
            "State the intended uses of the reference standard "
            "(e.g. identification, purity testing, potency/assay)."
        )
    _as01_docs, _as01_ev = _refs_for_criterion(
        ['intended use', 'source', 'reference standard', 'analytical', 'identification', 'assay']
    )
    criteria.append(S5CriterionResult(
        criterion_id="S5-AS-01",
        criterion_title="Reference-standard sources and intended analytical uses",
        applicability="APPLICABLE",
        extracted_info=_as01_info,
        regulatory_guidance="IPRP QWGG S.5 assessment point (i)",
        assessment_finding=(
            f"Source: {claim.reference_standard_source_detail or 'NOT PROVIDED'}. "
            f"Intended use: {', '.join(claim.intended_use) if claim.intended_use else 'NOT DECLARED'}."
        ),
        missing_info=_as01_missing,
        supporting_documents=_as01_docs,
        evidence_verification_status="MISSING" if _as01_missing else _as01_ev,
        assessor_questions=_as01_questions,
    ))

    # ── S5-AS-02: Primary standard preparation, characterisation, purity, batch ─
    _as02_info: dict = {
        "lot_number": claim.lot_number,
        "coa_submitted": claim.coa_submitted,
        "ir_spectra_submitted": claim.ir_spectra_submitted,
        "purity_assignment": (
            claim.purity_assignment.model_dump() if claim.purity_assignment else None
        ),
        "assigned_content": claim.assigned_content,
        "official_standard_designation": (
            claim.official_standard_designation.model_dump()
            if claim.official_standard_designation else None
        ),
    }
    _as02_missing = []
    _as02_questions = []
    if claim.coa_submitted is None:
        _as02_missing.append(
            "coa_submitted not stated — IPRP sub-item (b): "
            "state whether CoA has been submitted"
        )
        _as02_questions.append("Confirm whether a Certificate of Analysis has been submitted for the primary RS.")
    elif claim.coa_submitted is False:
        _as02_missing.append(
            "coa_submitted = False — CoA for primary RS not submitted; required by IPRP sub-item (b)"
        )
        _as02_questions.append("Provide the CoA for the primary reference standard.")
    # IR spectra: required to be STATED per IPRP sub-item (b).
    # Absence of IR spectra is only a gap for in-house primary standards; for
    # compendial standards it is an assessor consideration, not automatic non-compliance.
    if claim.ir_spectra_submitted is None:
        _as02_missing.append(
            "ir_spectra_submitted not stated — IPRP sub-item (b): "
            "state whether overlaid IR spectra have been submitted"
        )
        _as02_questions.append("Confirm whether overlaid IR spectra have been submitted.")
    elif claim.ir_spectra_submitted is False and _is_inhouse(claim):
        # In-house primary RS: IR is required for characterisation (IPRP S.5 / Ph. Eur. 5.12 §4-1)
        _as02_missing.append(
            "ir_spectra_submitted = False — overlaid IR spectra not submitted; "
            "required for in-house primary RS by IPRP sub-item (b) and Ph. Eur. 5.12 §4-1"
        )
        _as02_questions.append("Submit overlaid IR spectra confirming identity of the in-house primary RS.")
    if claim.purity_assignment is None:
        _as02_missing.append(
            "purity_assignment not provided — Ph. Eur. 5.12 §4-2-3: "
            "structured purity assignment required for CRS used in quantitative analysis"
        )
        _as02_questions.append(
            "Provide the purity assignment method, value and traceability for the primary RS "
            "(e.g. mass balance, 99.5%, traceable to USP CRS)."
        )
    if claim.assigned_content is None:
        _as02_missing.append(
            "assigned_content not provided — numeric purity/content value from CoA required"
        )
        _as02_questions.append(
            "State the assigned content (purity %) from the CoA for the primary RS lot."
        )
    _as02_docs, _as02_ev = _refs_for_criterion(
        ['primary standard', 'purity', 'characterisation', 'batch', 'certificate']
    )
    criteria.append(S5CriterionResult(
        criterion_id="S5-AS-02",
        criterion_title="Primary standard preparation, characterisation, purity and batch number",
        applicability="APPLICABLE",
        extracted_info=_as02_info,
        regulatory_guidance="IPRP QWGG S.5 assessment point (ii); Ph. Eur. 5.12 §4-2",
        assessment_finding=(
            f"Lot: {claim.lot_number or 'NOT PROVIDED'}. "
            f"CoA submitted: {claim.coa_submitted}. "
            f"IR spectra submitted: {claim.ir_spectra_submitted}. "
            f"Purity assignment: {'provided' if claim.purity_assignment else 'NOT PROVIDED'}. "
            f"Assigned content: {f'{claim.assigned_content}%' if claim.assigned_content is not None else 'NOT PROVIDED'}."
        ),
        missing_info=_as02_missing,
        supporting_documents=_as02_docs,
        evidence_verification_status="MISSING" if _as02_missing else _as02_ev,
        assessor_questions=_as02_questions,
    ))

    # ── S5-AS-03: Secondary standard identification, purity and batch ─────────
    _as03_info: dict = {
        "working_standard_lot": claim.working_standard_lot,
        "working_standard_source": claim.working_standard_source,
        "working_standard_assay": claim.working_standard_assay,
        "batch_validity_statement": (
            claim.batch_validity_statement.model_dump()
            if claim.batch_validity_statement else None
        ),
    }
    _as03_missing = []
    _as03_questions = []
    if not claim.working_standard_lot:
        _as03_missing.append(
            "working_standard_lot not provided — lot number of secondary/working standard required"
        )
        _as03_questions.append(
            "Provide the lot/batch number of the secondary/working standard."
        )
    if claim.working_standard_assay is None:
        _as03_missing.append(
            "working_standard_assay not provided — "
            "IPRP assessment point (iii): assigned purity of secondary standard required"
        )
        _as03_questions.append(
            "State the assigned purity value of the working standard "
            "(e.g. 100.4% on anhydrous basis)."
        )
    _as03_docs, _as03_ev = _refs_for_criterion(
        ['secondary standard', 'working standard', 'assay', 'purity', 'batch', 'lot']
    )
    criteria.append(S5CriterionResult(
        criterion_id="S5-AS-03",
        criterion_title="Secondary standard identification, assigned purity and batch number",
        applicability="APPLICABLE",
        extracted_info=_as03_info,
        regulatory_guidance="IPRP QWGG S.5 assessment point (iii); Ph. Eur. 5.12 §4-5",
        assessment_finding=(
            f"Working std lot: {claim.working_standard_lot or 'NOT PROVIDED'}. "
            f"Source: {claim.working_standard_source or 'NOT PROVIDED'}. "
            f"Assigned purity: {f'{claim.working_standard_assay}%' if claim.working_standard_assay is not None else 'NOT PROVIDED'}. "
            f"BVS: {'provided' if claim.batch_validity_statement else 'NOT PROVIDED'}."
        ),
        missing_info=_as03_missing,
        supporting_documents=_as03_docs,
        evidence_verification_status="MISSING" if _as03_missing else _as03_ev,
        assessor_questions=_as03_questions,
    ))

    # ── S5-AS-04: Impurity standards ──────────────────────────────────────────
    _as04_docs, _as04_ev = _refs_for_criterion(
        ['impurity', 'impurity standard', 'degradant', 'related substance', 'limit test']
    )
    if claim.impurity_standards is None:
        criteria.append(S5CriterionResult(
            criterion_id="S5-AS-04",
            criterion_title="Impurity standard characterisation and purity (where applicable)",
            applicability="NOT_PROVIDED",
            extracted_info=None,
            regulatory_guidance="IPRP QWGG S.5 assessment point (iv)",
            assessment_finding=(
                "Impurity standards not declared in this claim. "
                "Applicant must confirm whether impurity standards are used for this drug substance."
            ),
            missing_info=[
                "impurity_standards not declared — applicant must state if applicable; "
                "if used, provide characterisation and purity for each"
            ],
            supporting_documents=_as04_docs,
            evidence_verification_status=_as04_ev,
            assessor_questions=[
                "Confirm whether impurity reference standards are used for this drug substance. "
                "If yes, provide characterisation methods and assigned purity for each."
            ],
        ))
    elif len(claim.impurity_standards) == 0:
        criteria.append(S5CriterionResult(
            criterion_id="S5-AS-04",
            criterion_title="Impurity standard characterisation and purity (where applicable)",
            applicability="APPLICABLE",
            extracted_info={"impurity_standards": []},
            regulatory_guidance="IPRP QWGG S.5 assessment point (iv)",
            assessment_finding="Impurity standards list declared but contains no entries.",
            missing_info=["impurity_standards list is empty — provide at least one entry if applicable"],
            supporting_documents=_as04_docs,
            evidence_verification_status="MISSING",
            assessor_questions=[
                "Impurity standards list was declared as empty. "
                "Confirm whether impurity standards are applicable and provide entries if so."
            ],
        ))
    else:
        _as04_info_list = []
        _as04_missing = []
        _as04_questions = []
        for imp in claim.impurity_standards:
            _as04_info_list.append({
                "official_name": imp.official_name,
                "source": imp.source,
                "purity_percent": imp.purity_percent,
                "coa_available": imp.coa_available,
                "is_primary": imp.is_primary,
                "characterisation_methods": imp.characterisation_methods,
            })
            if imp.purity_percent is None:
                _as04_missing.append(
                    f"impurity standard '{imp.official_name}': purity_percent not assigned — "
                    "IPRP assessment point (iv): assigned purity required"
                )
                _as04_questions.append(
                    f"Provide the assigned purity value for impurity standard '{imp.official_name}'."
                )
            if not imp.characterisation_methods:
                _as04_missing.append(
                    f"impurity standard '{imp.official_name}': characterisation_methods not provided — "
                    "IPRP assessment point (iv): characterisation required (e.g. IR, NMR, MS)"
                )
                _as04_questions.append(
                    f"Provide the characterisation methods used for impurity standard '{imp.official_name}' "
                    "(e.g. IR, NMR, MS)."
                )
        criteria.append(S5CriterionResult(
            criterion_id="S5-AS-04",
            criterion_title="Impurity standard characterisation and purity (where applicable)",
            applicability="APPLICABLE",
            extracted_info={"impurity_standards": _as04_info_list},
            regulatory_guidance="IPRP QWGG S.5 assessment point (iv)",
            assessment_finding=(
                f"{len(claim.impurity_standards)} impurity standard(s) declared. "
                + (
                    "All have assigned purity and characterisation methods."
                    if not _as04_missing else
                    f"{len(_as04_missing)} gap(s) identified."
                )
            ),
            missing_info=_as04_missing,
            supporting_documents=_as04_docs,
            evidence_verification_status="MISSING" if _as04_missing else "NOT_VERIFIED",
            assessor_questions=_as04_questions,
        ))

    # ── Consolidate QA review summary ─────────────────────────────────────────
    _all_gaps: list[str] = []
    for c in criteria:
        if c.applicability == "APPLICABLE":
            _all_gaps.extend(c.missing_info)

    _qa_summary = S5QAReviewSummary(
        qa_status=finding.qa_status,
        rule_references=finding.rule_references,
        gaps=_all_gaps,
    )

    return S5AssessmentReport(
        substance_name=claim.substance_name,
        standard_claimed=claim.standard,
        generated_at=_now,
        source_note=finding.source_note,
        criteria=criteria,
        qa_review=_qa_summary,
    )


# ---------------------------------------------------------------------------
# Phase 3 — Dossier claim extraction  (additive; no existing code changed)
# ---------------------------------------------------------------------------

import re as _re  # noqa: E402 — appended after main module body

