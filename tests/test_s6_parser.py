"""
Tests for src/container_closure/parser.py — Phase 4a.

Verifies:
* Valid claims are accepted and returned in ParsedClaimSet.accepted.
* Each rejection rule (R1–R4) rejects the right claim with the right
  reason code and a non-empty detail message.
* Non-S6Claim inputs produce ParseRejection with reason "invalid_input".
* Mixed batches are split correctly with no silent drops.
* An empty input sequence produces an empty ParsedClaimSet.
* Accepted claims preserve all fields (source_ref, packaging_components,
  batch_numbers, quantitative_values, context).
* ParsedClaimSet.has_accepted and .total_input_count are correct.
* Every input item appears in exactly one of accepted or rejected
  (no silent drops, no duplicates).
"""
from __future__ import annotations

import pytest

from container_closure.parser import (
    ParsedClaimSet,
    ParseRejection,
    parse_claims,
    _REASON_BAD_SOURCE_REF,
    _REASON_EMPTY_ID,
    _REASON_EMPTY_TEXT,
    _REASON_INVALID_INPUT,
    _REASON_WRONG_SECTION,
)
from shared.models import S6Claim, SourceReference
from tests.fixtures.s6_fixtures import (
    fixture_claim_bad_source_ref_no_id,
    fixture_claim_bad_source_ref_no_type,
    fixture_claim_empty_id,
    fixture_claim_empty_text,
    fixture_claim_minimal_optional_fields,
    fixture_claim_with_stability_reference,
    fixture_claim_wrong_section,
    fixture_valid_claim,
)


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


class TestEmptyInput:
    def test_empty_sequence_returns_empty_set(self):
        result = parse_claims([])
        assert isinstance(result, ParsedClaimSet)
        assert result.accepted == []
        assert result.rejected == []

    def test_has_accepted_false_for_empty(self):
        assert not parse_claims([]).has_accepted

    def test_total_count_zero_for_empty(self):
        assert parse_claims([]).total_input_count == 0


# ---------------------------------------------------------------------------
# Valid claims
# ---------------------------------------------------------------------------


class TestValidClaims:
    def test_fully_populated_claim_is_accepted(self):
        claim = fixture_valid_claim()
        result = parse_claims([claim])
        assert len(result.accepted) == 1
        assert result.rejected == []

    def test_accepted_claim_id_matches(self):
        claim = fixture_valid_claim(claim_id="my-claim-99")
        result = parse_claims([claim])
        assert result.accepted[0].claim_id == "my-claim-99"

    def test_minimal_optional_fields_accepted(self):
        """A claim with no batch_numbers / packaging_components / etc. must
        still be accepted — missing optional fields are INSUFFICIENT_DATA
        at evaluation time, not a parser rejection."""
        claim = fixture_claim_minimal_optional_fields()
        result = parse_claims([claim])
        assert len(result.accepted) == 1
        assert result.rejected == []

    def test_stability_reference_claim_accepted(self):
        claim = fixture_claim_with_stability_reference()
        result = parse_claims([claim])
        assert len(result.accepted) == 1

    def test_accepted_claim_preserves_source_ref(self):
        claim = fixture_valid_claim()
        result = parse_claims([claim])
        accepted = result.accepted[0]
        assert accepted.source_ref.source_type == "m3_extraction"
        assert accepted.source_ref.source_id == "doc-001"

    def test_accepted_claim_preserves_packaging_components(self):
        claim = fixture_valid_claim(packaging_components=["glass vial", "rubber stopper"])
        result = parse_claims([claim])
        assert result.accepted[0].packaging_components == ["glass vial", "rubber stopper"]

    def test_accepted_claim_preserves_batch_numbers(self):
        claim = fixture_valid_claim(batch_numbers=["BN-001", "BN-002"])
        result = parse_claims([claim])
        assert result.accepted[0].batch_numbers == ["BN-001", "BN-002"]

    def test_accepted_claim_preserves_quantitative_values(self):
        claim = fixture_valid_claim(quantitative_values={"volume_mL": "10", "fill_weight_g": "5.2"})
        result = parse_claims([claim])
        assert result.accepted[0].quantitative_values == {"volume_mL": "10", "fill_weight_g": "5.2"}

    def test_has_accepted_true_when_claims_accepted(self):
        result = parse_claims([fixture_valid_claim()])
        assert result.has_accepted

    def test_multiple_valid_claims_all_accepted(self):
        claims = [fixture_valid_claim(claim_id=f"c-{i:03d}") for i in range(10)]
        result = parse_claims(claims)
        assert len(result.accepted) == 10
        assert result.rejected == []

    def test_total_count_matches_input_length(self):
        claims = [fixture_valid_claim(claim_id=f"c-{i:03d}") for i in range(7)]
        result = parse_claims(claims)
        assert result.total_input_count == 7

    def test_section_s6_accepted(self):
        claim = fixture_valid_claim()
        assert claim.section == "S.6"
        result = parse_claims([claim])
        assert len(result.accepted) == 1

    def test_other_s_dot_sections_accepted(self):
        """S.1, S.2, etc. are allowed; only non-S.* sections are rejected."""
        claim = fixture_valid_claim()
        # Manually build a claim with section "S.1"
        s1_claim = S6Claim(
            claim_id="c-s1",
            text="General information claim.",
            source_ref=claim.source_ref,
            section="S.1",
        )
        result = parse_claims([s1_claim])
        assert len(result.accepted) == 1


# ---------------------------------------------------------------------------
# R1: empty claim_id
# ---------------------------------------------------------------------------


class TestR1EmptyClaimId:
    def test_whitespace_id_is_rejected(self):
        claim = fixture_claim_empty_id()
        result = parse_claims([claim])
        assert len(result.rejected) == 1
        assert result.accepted == []

    def test_rejection_reason_is_empty_id(self):
        claim = fixture_claim_empty_id()
        result = parse_claims([claim])
        assert result.rejected[0].reason == _REASON_EMPTY_ID

    def test_rejection_detail_is_non_empty(self):
        claim = fixture_claim_empty_id()
        result = parse_claims([claim])
        assert result.rejected[0].detail.strip() != ""

    def test_rejected_claim_id_is_empty_placeholder(self):
        claim = fixture_claim_empty_id()
        result = parse_claims([claim])
        assert result.rejected[0].claim_id == "<empty>"

    def test_raw_input_preserved_in_rejection(self):
        claim = fixture_claim_empty_id()
        result = parse_claims([claim])
        assert result.rejected[0].raw_input is claim


# ---------------------------------------------------------------------------
# R2: empty text
# ---------------------------------------------------------------------------


class TestR2EmptyText:
    def test_whitespace_text_is_rejected(self):
        claim = fixture_claim_empty_text()
        result = parse_claims([claim])
        assert len(result.rejected) == 1
        assert result.accepted == []

    def test_rejection_reason_is_empty_text(self):
        result = parse_claims([fixture_claim_empty_text()])
        assert result.rejected[0].reason == _REASON_EMPTY_TEXT

    def test_rejection_includes_claim_id(self):
        result = parse_claims([fixture_claim_empty_text()])
        assert "c-empty-text" in result.rejected[0].detail

    def test_raw_input_preserved(self):
        claim = fixture_claim_empty_text()
        result = parse_claims([claim])
        assert result.rejected[0].raw_input is claim


# ---------------------------------------------------------------------------
# R3: bad source_ref
# ---------------------------------------------------------------------------


class TestR3BadSourceRef:
    def test_empty_source_type_rejected(self):
        result = parse_claims([fixture_claim_bad_source_ref_no_type()])
        assert len(result.rejected) == 1
        assert result.rejected[0].reason == _REASON_BAD_SOURCE_REF

    def test_whitespace_source_id_rejected(self):
        result = parse_claims([fixture_claim_bad_source_ref_no_id()])
        assert len(result.rejected) == 1
        assert result.rejected[0].reason == _REASON_BAD_SOURCE_REF

    def test_rejection_includes_both_values_in_detail(self):
        result = parse_claims([fixture_claim_bad_source_ref_no_type()])
        detail = result.rejected[0].detail
        assert "source_type" in detail or "source_id" in detail

    def test_claim_id_preserved_in_rejection(self):
        result = parse_claims([fixture_claim_bad_source_ref_no_type()])
        assert result.rejected[0].claim_id == "c-bad-src"


# ---------------------------------------------------------------------------
# R4: wrong section
# ---------------------------------------------------------------------------


class TestR4WrongSection:
    def test_p_section_rejected(self):
        result = parse_claims([fixture_claim_wrong_section()])
        assert len(result.rejected) == 1
        assert result.rejected[0].reason == _REASON_WRONG_SECTION

    def test_rejection_detail_mentions_section(self):
        result = parse_claims([fixture_claim_wrong_section()])
        assert "P.3" in result.rejected[0].detail

    def test_p_section_claim_id_preserved(self):
        result = parse_claims([fixture_claim_wrong_section()])
        assert result.rejected[0].claim_id == "c-wrong-section"

    @pytest.mark.parametrize("section", ["P.1", "P.2", "P.3", "P.8", "INTRO", "1.0", "X.6"])
    def test_various_non_s_sections_rejected(self, section: str):
        claim = S6Claim(
            claim_id=f"c-{section}",
            text="Some text.",
            source_ref=SourceReference(
                source_type="m3_extraction",
                source_id="doc-001",
                section=section,
            ),
            section=section,
        )
        result = parse_claims([claim])
        assert len(result.rejected) == 1
        assert result.rejected[0].reason == _REASON_WRONG_SECTION


# ---------------------------------------------------------------------------
# Non-S6Claim input
# ---------------------------------------------------------------------------


class TestInvalidInput:
    def test_string_input_produces_invalid_input_rejection(self):
        result = parse_claims(["not a claim"])
        assert len(result.rejected) == 1
        assert result.rejected[0].reason == _REASON_INVALID_INPUT

    def test_integer_input_rejected(self):
        result = parse_claims([42])
        assert result.rejected[0].reason == _REASON_INVALID_INPUT

    def test_dict_input_rejected(self):
        result = parse_claims([{"claim_id": "x", "text": "y"}])
        assert result.rejected[0].reason == _REASON_INVALID_INPUT

    def test_none_input_rejected(self):
        result = parse_claims([None])
        assert result.rejected[0].reason == _REASON_INVALID_INPUT

    def test_invalid_input_claim_id_is_unknown_placeholder(self):
        result = parse_claims(["bad"])
        assert result.rejected[0].claim_id == "<unknown>"

    def test_raw_input_preserved_for_invalid(self):
        result = parse_claims(["bad"])
        assert result.rejected[0].raw_input == "bad"


# ---------------------------------------------------------------------------
# Mixed batches
# ---------------------------------------------------------------------------


class TestMixedBatches:
    def test_mixed_valid_and_invalid_split_correctly(self):
        inputs = [
            fixture_valid_claim(claim_id="good-1"),
            fixture_claim_empty_text(),
            fixture_valid_claim(claim_id="good-2"),
            fixture_claim_wrong_section(),
            "not a claim",
        ]
        result = parse_claims(inputs)
        assert len(result.accepted) == 2
        assert len(result.rejected) == 3

    def test_total_count_is_sum_of_accepted_and_rejected(self):
        inputs = [
            fixture_valid_claim(claim_id="good-1"),
            fixture_claim_empty_id(),
            fixture_claim_empty_text(),
        ]
        result = parse_claims(inputs)
        assert result.total_input_count == 3
        assert result.total_input_count == len(result.accepted) + len(result.rejected)

    def test_no_silent_drops(self):
        """Every input must appear exactly once in accepted or rejected."""
        claims = [fixture_valid_claim(claim_id=f"c-{i:03d}") for i in range(5)]
        bad = [fixture_claim_empty_text(), fixture_claim_wrong_section()]
        inputs = claims + bad
        result = parse_claims(inputs)
        assert result.total_input_count == 7

    def test_has_accepted_false_when_all_rejected(self):
        result = parse_claims([fixture_claim_empty_id(), fixture_claim_empty_text()])
        assert not result.has_accepted

    def test_accepted_order_preserved(self):
        """Accepted claims must appear in the same order as the input."""
        ids = [f"c-{i:03d}" for i in range(6)]
        claims = [fixture_valid_claim(claim_id=cid) for cid in ids]
        result = parse_claims(claims)
        assert [c.claim_id for c in result.accepted] == ids

    def test_all_rejection_types_in_one_batch(self):
        inputs = [
            fixture_claim_empty_id(),
            fixture_claim_empty_text(),
            fixture_claim_bad_source_ref_no_type(),
            fixture_claim_bad_source_ref_no_id(),
            fixture_claim_wrong_section(),
            "not a claim",
        ]
        result = parse_claims(inputs)
        reasons = {r.reason for r in result.rejected}
        assert _REASON_EMPTY_ID in reasons
        assert _REASON_EMPTY_TEXT in reasons
        assert _REASON_BAD_SOURCE_REF in reasons
        assert _REASON_WRONG_SECTION in reasons
        assert _REASON_INVALID_INPUT in reasons
