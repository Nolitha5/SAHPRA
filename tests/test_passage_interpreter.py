"""
Tests for src/container_closure/passage_interpreter.py (Phase 5b).

IMPORTANT: every InterpretationRuleset used below is synthetic test
data constructed to exercise the classification MECHANISM only. None
of it is a pharmacist-approved regulatory interpretation, and passing
these tests proves nothing about any real passage's regulatory status.
"""
from __future__ import annotations

from container_closure.evaluator import PassageInterpretation, RetrievedPassage
from container_closure.passage_interpreter import (
    InterpretationRuleset,
    build_passage_interpreter,
)
from shared.models import SourceReference


def _passage(text: str, passage_id: str = "p-001") -> RetrievedPassage:
    return RetrievedPassage(
        passage_id=passage_id,
        originating_question_id="q-001",
        ctd_section="3.2.S.6",
        text=text,
        source_ref=SourceReference(source_type="m2_rkb", source_id=passage_id, section="3.2.S.6"),
    )


class TestNoRulesFailsClosed:
    def test_none_rules_classifies_whole_passage_as_uncertain(self) -> None:
        passage = _passage("[SYNTHETIC TEST DATA] Some passage text.")
        interpret = build_passage_interpreter(None)
        statements = interpret(passage, None)
        assert len(statements) == 1
        assert statements[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION
        assert statements[0].boundary_confidence == "uncertain"
        assert statements[0].statement_text == passage.text

    def test_empty_ruleset_behaves_identically_to_none(self) -> None:
        passage = _passage("[SYNTHETIC TEST DATA] Some passage text.")
        interpret = build_passage_interpreter(InterpretationRuleset())
        statements = interpret(passage, None)
        assert len(statements) == 1
        assert statements[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION

    def test_strongly_normative_looking_text_still_resolves_to_uncertain_without_rules(self) -> None:
        """A statement full of 'shall'/'must'/'required' language must
        NOT become a confirmed requirement just because it reads that
        way -- modal language alone is never sufficient."""
        passage = _passage(
            "[SYNTHETIC TEST DATA] The container closure system shall, "
            "must, and is required to maintain integrity at all times."
        )
        interpret = build_passage_interpreter(None)
        statements = interpret(passage, None)
        assert len(statements) == 1
        assert statements[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION

    def test_empty_passage_text_yields_no_statements(self) -> None:
        passage = _passage("   ")
        interpret = build_passage_interpreter(None)
        assert interpret(passage, None) == []


class TestWithSyntheticRules:
    def test_requirement_pattern_match_classifies_as_potentially_applicable_requirement(self) -> None:
        passage = _passage("[SYNTHETIC TEST DATA] The closure must pass a leak test.")
        rules = InterpretationRuleset(requirement_patterns=("must pass a leak test",))
        interpret = build_passage_interpreter(rules)
        statements = interpret(passage, None)
        assert len(statements) == 1
        assert statements[0].interpretation == PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT
        assert statements[0].boundary_confidence == "confident"

    def test_not_applicable_pattern_match_classifies_as_not_applicable(self) -> None:
        passage = _passage("[SYNTHETIC TEST DATA] This section does not apply to this dosage form.")
        rules = InterpretationRuleset(not_applicable_patterns=("does not apply",))
        interpret = build_passage_interpreter(rules)
        statements = interpret(passage, None)
        assert statements[0].interpretation == PassageInterpretation.NOT_APPLICABLE

    def test_supporting_pattern_match_classifies_as_supporting_information(self) -> None:
        passage = _passage("[SYNTHETIC TEST DATA] For background, see the general introduction.")
        rules = InterpretationRuleset(supporting_information_patterns=("for background",))
        interpret = build_passage_interpreter(rules)
        statements = interpret(passage, None)
        assert statements[0].interpretation == PassageInterpretation.SUPPORTING_INFORMATION

    def test_no_pattern_match_falls_back_to_uncertain(self) -> None:
        passage = _passage("[SYNTHETIC TEST DATA] Nothing here matches any supplied pattern.")
        rules = InterpretationRuleset(requirement_patterns=("completely unrelated phrase",))
        interpret = build_passage_interpreter(rules)
        statements = interpret(passage, None)
        assert statements[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION
        assert statements[0].boundary_confidence == "uncertain"

    def test_conflicting_cross_category_match_falls_back_to_uncertain_not_a_guess(self) -> None:
        """A statement matching patterns from two different categories
        must never be resolved by picking one -- it falls back to
        UNCERTAIN_INTERPRETATION."""
        passage = _passage("[SYNTHETIC TEST DATA] This must be tested but does not apply here.")
        rules = InterpretationRuleset(
            requirement_patterns=("must be tested",),
            not_applicable_patterns=("does not apply",),
        )
        interpret = build_passage_interpreter(rules)
        statements = interpret(passage, None)
        assert statements[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION
        assert statements[0].boundary_confidence == "uncertain"

    def test_multi_sentence_passage_splits_and_classifies_each_statement(self) -> None:
        passage = _passage(
            "[SYNTHETIC TEST DATA] The closure must pass a leak test. "
            "For background, see the general introduction."
        )
        rules = InterpretationRuleset(
            requirement_patterns=("must pass a leak test",),
            supporting_information_patterns=("for background",),
        )
        interpret = build_passage_interpreter(rules)
        statements = interpret(passage, None)
        assert len(statements) == 2
        interpretations = {s.interpretation for s in statements}
        assert PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT in interpretations
        assert PassageInterpretation.SUPPORTING_INFORMATION in interpretations

    def test_every_statement_span_is_an_exact_verbatim_substring(self) -> None:
        passage = _passage(
            "[SYNTHETIC TEST DATA] The closure must pass a leak test. "
            "For background, see the general introduction."
        )
        rules = InterpretationRuleset(
            requirement_patterns=("must pass a leak test",),
            supporting_information_patterns=("for background",),
        )
        interpret = build_passage_interpreter(rules)
        for stmt in interpret(passage, None):
            assert stmt.span is not None
            start, end = stmt.span
            assert passage.text[start:end] == stmt.statement_text

    def test_empty_passage_text_yields_no_statements_with_rules_too(self) -> None:
        passage = _passage("")
        rules = InterpretationRuleset(requirement_patterns=("anything",))
        interpret = build_passage_interpreter(rules)
        assert interpret(passage, None) == []
