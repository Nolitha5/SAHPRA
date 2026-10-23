"""
pytest suite for s5_standards.py.

Covers:
  - current edition matches claim → COMPLIANT
  - outdated edition claimed → NON_COMPLIANT
  - unknown standard/substance → NEEDS_REVIEW
  - submission date before any record exists → NEEDS_REVIEW
  - case-insensitive edition comparison
  - source_note is always present and never empty
  - citation is populated for COMPLIANT and NON_COMPLIANT
  - citation is None for NEEDS_REVIEW
  - custom repository (Protocol) can be substituted (replaceability test)
"""

from datetime import date

import pytest

from models import S5Claim, S5Finding
from s5_standards import (
    MockMonographRepository,
    MonographRecord,
    check_s5_claim,
)


# ── Helpers ──────────────────────────────────────────────────────────

def make_claim(**overrides) -> S5Claim:
    defaults = dict(
        substance_name="Ethanol",
        standard="BP",
        edition_claimed="BP 2024",
        submission_date=date(2024, 3, 1),
    )
    defaults.update(overrides)
    return S5Claim(**defaults)


repo = MockMonographRepository()


# ── COMPLIANT cases ───────────────────────────────────────────────────

def test_current_edition_is_compliant():
    claim = make_claim(edition_claimed="BP 2024", submission_date=date(2024, 3, 1))
    result = check_s5_claim(claim, repo)
    assert result.verdict == "COMPLIANT"


def test_compliant_result_has_citation():
    claim = make_claim(edition_claimed="BP 2024", submission_date=date(2024, 3, 1))
    result = check_s5_claim(claim, repo)
    assert result.citation is not None and result.citation.strip() != ""


def test_edition_comparison_is_case_insensitive():
    claim = make_claim(edition_claimed="bp 2024", submission_date=date(2024, 3, 1))
    result = check_s5_claim(claim, repo)
    assert result.verdict == "COMPLIANT"


def test_usp_current_edition_compliant():
    claim = make_claim(
        substance_name="Aspirin",
        standard="USP",
        edition_claimed="USP 47",
        submission_date=date(2024, 6, 1),
    )
    result = check_s5_claim(claim, repo)
    assert result.verdict == "COMPLIANT"


# ── NON_COMPLIANT cases ───────────────────────────────────────────────

def test_outdated_edition_is_non_compliant():
    # Submission in 2024 but claiming BP 2019
    claim = make_claim(edition_claimed="BP 2019", submission_date=date(2024, 3, 1))
    result = check_s5_claim(claim, repo)
    assert result.verdict == "NON_COMPLIANT"


def test_non_compliant_reports_current_edition():
    claim = make_claim(edition_claimed="BP 2019", submission_date=date(2024, 3, 1))
    result = check_s5_claim(claim, repo)
    assert result.edition_current == "BP 2024"


def test_non_compliant_has_citation():
    claim = make_claim(edition_claimed="BP 2019", submission_date=date(2024, 3, 1))
    result = check_s5_claim(claim, repo)
    assert result.citation is not None and result.citation.strip() != ""


def test_intermediate_edition_at_submission_date():
    # Submission in 2020: BP 2020 was current, claiming BP 2019 → NON_COMPLIANT
    claim = make_claim(edition_claimed="BP 2019", submission_date=date(2020, 6, 1))
    result = check_s5_claim(claim, repo)
    assert result.verdict == "NON_COMPLIANT"
    assert result.edition_current == "BP 2020"


# ── NEEDS_REVIEW cases ────────────────────────────────────────────────

def test_unknown_standard_needs_review():
    claim = make_claim(standard="Ph.Eur.", substance_name="Ethanol")
    result = check_s5_claim(claim, repo)
    assert result.verdict == "NEEDS_REVIEW"


def test_unknown_substance_needs_review():
    claim = make_claim(substance_name="UnknownDrug123")
    result = check_s5_claim(claim, repo)
    assert result.verdict == "NEEDS_REVIEW"


def test_submission_before_any_record_needs_review():
    # Submission in 2010, before BP 2019 record exists
    claim = make_claim(submission_date=date(2010, 1, 1))
    result = check_s5_claim(claim, repo)
    assert result.verdict == "NEEDS_REVIEW"


def test_needs_review_citation_is_none():
    claim = make_claim(standard="Ph.Eur.", substance_name="Ethanol")
    result = check_s5_claim(claim, repo)
    assert result.citation is None


# ── Invariants for all verdicts ───────────────────────────────────────

@pytest.mark.parametrize("edition,sub_date,expected_verdict", [
    ("BP 2024", date(2024, 3, 1), "COMPLIANT"),
    ("BP 2019", date(2024, 3, 1), "NON_COMPLIANT"),
    ("BP 2024", date(2024, 3, 1), "COMPLIANT"),
])
def test_source_note_always_present(edition, sub_date, expected_verdict):
    claim = make_claim(edition_claimed=edition, submission_date=sub_date)
    result = check_s5_claim(claim, repo)
    assert result.verdict == expected_verdict
    assert result.source_note and result.source_note.strip() != ""


def test_needs_review_source_note_present():
    claim = make_claim(standard="Ph.Eur.")
    result = check_s5_claim(claim, repo)
    assert result.source_note and result.source_note.strip() != ""


# ── Replaceability: custom repository ────────────────────────────────

class _SingleRecordRepo:
    """Minimal stub that returns one fixed record, proving the Protocol works."""

    def get_current_edition(self, standard, substance_name, as_of):
        return MonographRecord(
            standard="BP",
            substance_name="testsubstance",
            edition="BP 2022",
            valid_from=date(2022, 1, 1),
            monograph_name="Test Substance",
            page="1",
            source_note="stub record",
        )


def test_custom_repository_is_accepted():
    claim = make_claim(
        substance_name="TestSubstance",
        standard="BP",
        edition_claimed="BP 2022",
        submission_date=date(2022, 6, 1),
    )
    result = check_s5_claim(claim, _SingleRecordRepo())
    assert result.verdict == "COMPLIANT"
