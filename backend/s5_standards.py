"""
S.5 Reference Standards agent.

Accepts a structured S5Claim and a MonographRepository, then:
  1. Checks completeness against the IPRP QWGG S.5 checklist (sub-items a–d).
  2. Looks up the pharmacopoeial monograph current at the submission date.
  3. Compares the sponsor's claimed edition to the retrieved current edition.
  4. Returns an S5Finding with:
       - verdict: COMPLIANT, NON_COMPLIANT, or NEEDS_REVIEW
       - completeness_flags: list of IPRP checklist items the applicant left blank

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

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from models import ReferenceStandardType, S5Claim, S5Finding


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
    # British Pharmacopoeia — Ethanol
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
    # United States Pharmacopeia — Aspirin
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
    # United States Pharmacopeia — Amlodipine Besylate
    # Based on real dossier: USP lot R09060; added to support Amlodipine test cases.
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
        as_of: date,
    ) -> MonographRecord | None:
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

    return flags


# ── Agent logic ───────────────────────────────────────────────────────────────

def check_s5_claim(
    claim: S5Claim,
    repository: MonographRepository,
) -> S5Finding:
    """
    Validate one S.5 sponsor claim against the IPRP checklist and the
    monograph repository.

    Steps:
      1. Run completeness check (all IPRP sub-items a–d).
      2. Look up the current edition in the repository.
      3. Compare claimed vs current edition → verdict.

    Returns an S5Finding with:
      COMPLIANT     if claimed edition == current edition at submission date.
      NON_COMPLIANT if a current edition exists and differs from claimed.
      NEEDS_REVIEW  if no record is available; no verdict is made.

    completeness_flags is populated regardless of verdict — a claim can be
    COMPLIANT on the edition check but still have missing IPRP sub-items.
    """
    completeness_flags = _check_completeness(claim)

    record = repository.get_current_edition(
        standard=claim.standard,
        substance_name=claim.substance_name,
        as_of=claim.submission_date,
    )

    if record is None:
        return S5Finding(
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
            verdict="NEEDS_REVIEW",
            verdict_reason=(
                "Reference information unavailable. "
                "Manual pharmacopoeial check required before a compliance verdict can be issued."
            ),
            source_note="No record available in the current repository.",
            completeness_flags=completeness_flags,
        )

    citation = (
        f"{record.monograph_name}, {record.edition}"
        + (f", p. {record.page}" if record.page else "")
    )

    if claim.edition_claimed.strip().upper() == record.edition.strip().upper():
        return S5Finding(
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
            verdict="COMPLIANT",
            verdict_reason="Claimed edition matches the current edition at submission date.",
            source_note=record.source_note,
            completeness_flags=completeness_flags,
        )
    else:
        return S5Finding(
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
            verdict="NON_COMPLIANT",
            verdict_reason=(
                f"Claimed edition ({claim.edition_claimed}) is not the current edition "
                f"({record.edition}) at submission date ({claim.submission_date})."
            ),
            source_note=record.source_note,
            completeness_flags=completeness_flags,
        )
