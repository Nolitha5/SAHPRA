"""
Tests for src/container_closure/applicability_classifier.py (Phase 5b).
"""
from __future__ import annotations

import inspect

from container_closure.applicability_classifier import (
    _assess_claim_specific_applicability,
    _assess_general_s6_relevance,
    classify_applicability,
)
from container_closure.evaluator import ApplicabilityConfidence, RetrievedPassage
from shared.models import S6Claim, SourceReference


def _passage(text: str = "[SYNTHETIC TEST DATA] Some passage text.") -> RetrievedPassage:
    return RetrievedPassage(
        passage_id="p-ac-001",
        originating_question_id="q-ac-001",
        ctd_section="3.2.S.6",
        text=text,
        source_ref=SourceReference(source_type="m2_rkb", source_id="p-ac-001", section="3.2.S.6"),
    )


def _claim(**overrides) -> S6Claim:
    defaults: dict = dict(
        claim_id="c-ac-001",
        text="[SYNTHETIC] Claim text.",
        source_ref=SourceReference(source_type="m3_extraction", source_id="d1", section="S.6"),
    )
    defaults.update(overrides)
    return S6Claim(**defaults)


class TestExternalFunctionAlwaysUncertain:
    def test_returns_uncertain_for_a_plain_claim_and_passage(self) -> None:
        assert classify_applicability(_passage(), _claim()) == ApplicabilityConfidence.UNCERTAIN

    def test_returns_uncertain_even_when_text_strongly_overlaps(self) -> None:
        passage = _passage("[SYNTHETIC TEST DATA] Type I glass vial with chlorobutyl stopper.")
        claim = _claim(
            text="[SYNTHETIC] Type I glass vial with chlorobutyl stopper.",
            packaging_components=["Type I glass vial", "chlorobutyl stopper"],
        )
        assert classify_applicability(passage, claim) == ApplicabilityConfidence.UNCERTAIN

    def test_returns_uncertain_for_an_empty_passage(self) -> None:
        assert classify_applicability(_passage(""), _claim()) == ApplicabilityConfidence.UNCERTAIN

    def test_never_returns_directly_relevant_or_possibly_relevant_today(self) -> None:
        for text in ("", "irrelevant", "[SYNTHETIC] vial stopper closure seal"):
            result = classify_applicability(_passage(text), _claim())
            assert result == ApplicabilityConfidence.UNCERTAIN


class TestInternalStepsAreSeparateAndIndependentlyTestable:
    def test_general_relevance_step_is_independently_callable_and_returns_none(self) -> None:
        assert _assess_general_s6_relevance(_passage()) is None

    def test_claim_specific_step_is_independently_callable_and_returns_none(self) -> None:
        assert _assess_claim_specific_applicability(_passage(), _claim()) is None

    def test_general_relevance_step_takes_only_a_passage(self) -> None:
        """Confirms the general-relevance step cannot see claim-specific
        content at all -- it is structurally a passage-only decision."""
        params = list(inspect.signature(_assess_general_s6_relevance).parameters)
        assert params == ["passage"]

    def test_claim_specific_step_takes_passage_and_claim(self) -> None:
        params = list(inspect.signature(_assess_claim_specific_applicability).parameters)
        assert params == ["passage", "claim"]


class TestSourceApprovalIsNeverThisModulesConcern:
    def test_retrieved_passage_carries_no_source_category_field_to_consult(self) -> None:
        """RetrievedPassage has no approved-category field at all, so
        this classifier structurally cannot re-derive or second-guess
        source approval -- confirmed by inspecting its own fields."""
        import dataclasses

        field_names = {f.name for f in dataclasses.fields(RetrievedPassage)}
        assert "approved_category" not in field_names
        assert "source_category" not in field_names

    def test_classify_applicability_signature_has_no_verification_status_parameter(self) -> None:
        params = list(inspect.signature(classify_applicability).parameters)
        assert params == ["passage", "claim"]
