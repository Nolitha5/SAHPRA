"""
Synthetic SCORE-style dossier claim fixtures (Phase 5a).

Used by tests/test_evaluator_integration.py and tests/test_evaluator.py's
parser-integration cases.

Rules (same as tests/fixtures/s6_fixtures.py and
tests/fixtures/evaluator_fixtures.py):
* No external service is called. Everything is in-memory.
* No regulatory content is invented or implied as genuine. Every claim's
  text is clearly labelled [SYNTHETIC] and is not a real SCORE dossier
  excerpt, a real sponsor claim, or a validated regulatory interpretation.
* fixture_ prefix on factories, matching project convention.
* Structurally-invalid claim fixtures (empty id/text, bad source_ref,
  wrong section) already exist in tests.fixtures.s6_fixtures (Phase 4a)
  and are re-exported here, not recreated, per the project's "fixtures
  reused across test files, not duplicated" convention.
"""
from __future__ import annotations

from typing import Any

from shared.models import S6Claim

from tests.fixtures.s6_fixtures import (
    fixture_claim_bad_source_ref_no_id,
    fixture_claim_bad_source_ref_no_type,
    fixture_claim_empty_id,
    fixture_claim_empty_text,
    fixture_claim_wrong_section,
    fixture_source_ref,
)

__all__ = [
    # Re-exported Phase 4a structural-rejection fixtures (R1-R4)
    "fixture_claim_bad_source_ref_no_id",
    "fixture_claim_bad_source_ref_no_type",
    "fixture_claim_empty_id",
    "fixture_claim_empty_text",
    "fixture_claim_wrong_section",
    # New Phase 5a fixtures
    "fixture_invalid_raw_claim_input",
    "fixture_score_claim_container_and_closure",
    "fixture_score_claim_self_assertion",
    "fixture_score_claim_storage_cross_reference",
]


# ---------------------------------------------------------------------------
# Accepted, realistic (synthetic) SCORE-style dossier claims
# ---------------------------------------------------------------------------


def fixture_score_claim_container_and_closure(claim_id: str = "score-claim-001") -> S6Claim:
    """[SYNTHETIC TEST DATA] A fully-specified primary container/closure
    claim, structurally valid under every parser check. Not a real
    sponsor dossier excerpt or a real regulatory requirement."""
    return S6Claim(
        claim_id=claim_id,
        text=(
            "[SYNTHETIC] The drug product is packaged in a 5 mL Type I clear "
            "borosilicate glass vial with a 20 mm chlorobutyl rubber stopper "
            "and aluminium flip-off seal; extractable/leachable study "
            "referenced, Batch BN-2026-014."
        ),
        source_ref=fixture_source_ref(
            source_id="score-doc-014", document="[SYNTHETIC] score_dossier_extract.pdf"
        ),
        packaging_components=["Type I glass vial", "chlorobutyl rubber stopper", "aluminium flip-off seal"],
        batch_numbers=["BN-2026-014"],
        quantitative_values={"volume_mL": "5", "stopper_diameter_mm": "20"},
    )


def fixture_score_claim_self_assertion(claim_id: str = "score-claim-002") -> S6Claim:
    """[SYNTHETIC TEST DATA] A sponsor's own assertion of compendial
    compliance, with no independently-presented test data in the claim
    text itself. Structurally valid; reserved for a later phase's test
    that a sponsor's own wording is never, by itself, treated as
    evidence of satisfaction. Not a real regulatory requirement."""
    return S6Claim(
        claim_id=claim_id,
        text=(
            "[SYNTHETIC] The rubber stopper complies with compendial "
            "requirements for elastomeric closures."
        ),
        source_ref=fixture_source_ref(
            source_id="score-doc-002", document="[SYNTHETIC] score_dossier_extract.pdf"
        ),
        packaging_components=["rubber stopper"],
    )


def fixture_score_claim_storage_cross_reference(claim_id: str = "score-claim-003") -> S6Claim:
    """[SYNTHETIC TEST DATA] A storage/packaging claim that also carries
    stability cross-reference signal, exercising the (unmodified) Phase
    4b S.6/S.7 cross-section boundary alongside regulatory evaluation.
    Not real stability data."""
    return S6Claim(
        claim_id=claim_id,
        text=(
            "[SYNTHETIC] HDPE bottle with child-resistant polypropylene "
            "closure, used in long-term and accelerated stability studies "
            "per the sponsor's own storage programme."
        ),
        source_ref=fixture_source_ref(
            source_id="score-doc-003", document="[SYNTHETIC] score_dossier_extract.pdf"
        ),
        packaging_components=["HDPE bottle", "polypropylene closure"],
        batch_numbers=["BN-2026-021"],
        quantitative_values={"study_duration_months": "24"},
    )


# ---------------------------------------------------------------------------
# A raw input that is not an S6Claim at all (-> parser "invalid_input")
# ---------------------------------------------------------------------------


def fixture_invalid_raw_claim_input() -> dict[str, Any]:
    """[SYNTHETIC TEST DATA] Represents a malformed/unparsed fragment
    that never became a valid S6Claim (e.g. upstream extraction
    produced a raw mapping instead of our own contract). Deliberately
    NOT an S6Claim instance, to exercise parser.parse_claims's
    'invalid_input' rejection path. Its 'claim_id'-shaped key is
    intentionally present to prove the evaluator never trusts an
    unvalidated attribute of a non-conforming object."""
    return {"claim_id": "score-claim-999", "text": "[SYNTHETIC] not a real S6Claim instance"}
