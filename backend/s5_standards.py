"""
S.5 Reference Standards agent.

Accepts a structured S5Claim and a MonographRepository, then:
  1. Looks up the pharmacopoeial monograph current at the submission date.
  2. Compares the sponsor's claimed edition to the retrieved current edition.
  3. Returns an S5Finding with verdict COMPLIANT, NON_COMPLIANT, or NEEDS_REVIEW.

MonographRepository is a Protocol (replaceable interface).  The mock
implementation (MockMonographRepository) uses explicitly labelled in-memory
records and is the only implementation used until M2's RKB is available.

This module NEVER invents monograph names, edition numbers, citations or
regulatory conclusions.  If the required information is not available it
returns NEEDS_REVIEW with a clear explanation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from models import S5Claim, S5Finding


# ── Replaceable interface ─────────────────────────────────────────────

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


# ── Mock implementation ───────────────────────────────────────────────

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


# ── Agent logic ───────────────────────────────────────────────────────

def check_s5_claim(
    claim: S5Claim,
    repository: MonographRepository,
) -> S5Finding:
    """
    Validate one S.5 sponsor claim against the monograph repository.

    Returns an S5Finding with:
      COMPLIANT     if claimed edition == current edition at submission date.
      NON_COMPLIANT if a current edition exists and differs from claimed.
      NEEDS_REVIEW  if no record is available; no verdict is made.
    """
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
        )
