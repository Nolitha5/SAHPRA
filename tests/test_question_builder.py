"""
Tests for src/container_closure/question_builder.py (Phase 5b).
"""
from __future__ import annotations

from container_closure.evaluator import RegulatoryQuestion
from container_closure.question_builder import build_regulatory_questions
from shared.models import S6Claim, SourceReference


def _claim(**overrides) -> S6Claim:
    defaults: dict = dict(
        claim_id="c-qb-001",
        text="[SYNTHETIC] Neutral packaging statement with no routing signal.",
        source_ref=SourceReference(source_type="m3_extraction", source_id="d1", section="S.6"),
    )
    defaults.update(overrides)
    return S6Claim(**defaults)


class TestNoSignalYieldsNoQuestions:
    def test_claim_with_no_trigger_signal_yields_empty_list(self) -> None:
        claim = _claim(text="[SYNTHETIC] A claim with no recognisable routing terms at all.")
        assert build_regulatory_questions(claim) == []


class TestEachObjectiveTrigger:
    def test_packaging_components_triggers_container_description(self) -> None:
        claim = _claim(
            text="[SYNTHETIC] Neutral text.",
            packaging_components=["Type I glass vial"],
        )
        objectives = {q.assessment_objective for q in build_regulatory_questions(claim)}
        assert "container_description" in objectives

    def test_closure_term_triggers_closure_components(self) -> None:
        claim = _claim(text="[SYNTHETIC] The rubber stopper and crimp seal are described here.")
        objectives = {q.assessment_objective for q in build_regulatory_questions(claim)}
        assert "closure_components" in objectives

    def test_extractable_term_triggers_compatibility(self) -> None:
        claim = _claim(text="[SYNTHETIC] An extractable and leachable study was performed.")
        objectives = {q.assessment_objective for q in build_regulatory_questions(claim)}
        assert "compatibility" in objectives

    def test_integrity_term_triggers_protection_and_integrity(self) -> None:
        claim = _claim(text="[SYNTHETIC] Container integrity and tamper-evidence are described.")
        objectives = {q.assessment_objective for q in build_regulatory_questions(claim)}
        assert "protection_and_integrity" in objectives

    def test_dates_trigger_storage_statements(self) -> None:
        claim = _claim(text="[SYNTHETIC] Neutral text.", dates=["2026-01-01"])
        objectives = {q.assessment_objective for q in build_regulatory_questions(claim)}
        assert "storage_statements" in objectives

    def test_storage_term_triggers_storage_statements(self) -> None:
        claim = _claim(text="[SYNTHETIC] Long-term and accelerated stability storage conditions are described.")
        objectives = {q.assessment_objective for q in build_regulatory_questions(claim)}
        assert "storage_statements" in objectives


class TestMultipleObjectivesAndStructure:
    def test_claim_touching_multiple_objectives_yields_multiple_distinct_questions(self) -> None:
        claim = _claim(
            text=(
                "[SYNTHETIC] HDPE bottle with polypropylene closure used in an "
                "accelerated stability study referencing extractable testing."
            ),
            packaging_components=["HDPE bottle", "polypropylene closure"],
        )
        questions = build_regulatory_questions(claim)
        assert len(questions) >= 3
        objectives = [q.assessment_objective for q in questions]
        assert len(objectives) == len(set(objectives))  # no duplicate objectives
        assert all(isinstance(q, RegulatoryQuestion) for q in questions)
        question_ids = [q.question_id for q in questions]
        assert len(question_ids) == len(set(question_ids))  # distinct ids

    def test_question_text_preserves_claim_id_and_claim_text_for_provenance(self) -> None:
        claim = _claim(
            claim_id="c-provenance-007",
            text="[SYNTHETIC] Type I glass vial with chlorobutyl stopper.",
            packaging_components=["Type I glass vial"],
        )
        questions = build_regulatory_questions(claim)
        assert questions, "expected at least one triggered objective"
        for q in questions:
            assert "c-provenance-007" in q.question
            assert claim.text in q.question

    def test_default_ctd_section_is_not_overridden(self) -> None:
        claim = _claim(packaging_components=["Type I glass vial"])
        questions = build_regulatory_questions(claim)
        assert questions
        for q in questions:
            assert q.ctd_sections == ("3.2.S.6",)

    def test_no_regulatory_requirement_text_is_invented(self) -> None:
        """The question text only ever asks what applicable guidance
        requires -- it never asserts that a requirement exists, what
        it says, or that the claim satisfies or breaches anything."""
        claim = _claim(packaging_components=["Type I glass vial"])
        questions = build_regulatory_questions(claim)
        assert questions
        for q in questions:
            lowered = q.question.lower()
            assert "complies" not in lowered
            assert "satisfies" not in lowered
            assert "breach" not in lowered
