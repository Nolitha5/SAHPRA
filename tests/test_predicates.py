"""
Tests for container_closure.predicates (Phase 5c).

Covers: citation-keyed lookup, correct predicate dispatch, unknown
citations resolving to INDETERMINATE, absence of keyword/text-matching
heuristics, compatibility with evaluator.py's existing Mapping
interface (via its own private `_evaluate_predicate`, not a
reimplementation of it), and clear synthetic labelling.
"""
from __future__ import annotations

import inspect

from shared.enums import Verdict
from shared.models import S6Claim

from container_closure.evaluator import (
    ApplicabilityConfidence,
    InterpretedRequirement,
    PredicateAssessment,
    PredicateOutcome,
    _evaluate_predicate,
)
from container_closure.predicates import (
    CitationPredicateRegistry,
    resolve_predicate,
)

from tests.fixtures.evaluator_fixtures import fixture_statement
from tests.fixtures.s6_fixtures import fixture_source_ref, fixture_valid_claim

# ---------------------------------------------------------------------------
# Synthetic, test-only citations and predicates -- carry no regulatory
# authority whatsoever.
# ---------------------------------------------------------------------------

SYNTHETIC_CITATION_A = "[SYNTHETIC TEST DATA] USP <671> Containers -- Permeation (test citation A)"
SYNTHETIC_CITATION_B = "[SYNTHETIC TEST DATA] USP <660> Glass -- Surface Treatment (test citation B)"
SYNTHETIC_CITATION_UNREGISTERED = "[SYNTHETIC TEST DATA] Unregistered test citation"


def _requirement_with_citation(
    citation: str,
    applicability: ApplicabilityConfidence = ApplicabilityConfidence.DIRECTLY_RELEVANT,
    requirement_id: str = "req-for-predicate-test",
) -> InterpretedRequirement:
    stmt = fixture_statement()
    return InterpretedRequirement(
        requirement_id=requirement_id,
        text=stmt.statement_text,
        citation=citation,
        primary_statement=stmt,
        applicability=applicability,
    )


def _synthetic_predicate_satisfied(
    claim: S6Claim, requirement: InterpretedRequirement  # noqa: ARG001
) -> PredicateAssessment:
    return PredicateAssessment(
        outcome=PredicateOutcome.SATISFIED,
        rationale="[SYNTHETIC TEST DATA] test predicate A always satisfied.",
        source_refs=(fixture_source_ref(),),
    )


def _synthetic_predicate_breached(
    claim: S6Claim, requirement: InterpretedRequirement  # noqa: ARG001
) -> PredicateAssessment:
    return PredicateAssessment(
        outcome=PredicateOutcome.BREACHED,
        rationale="[SYNTHETIC TEST DATA] test predicate B always breached.",
        source_refs=(fixture_source_ref(),),
    )


# ---------------------------------------------------------------------------
# Citation-keyed lookup / correct dispatch
# ---------------------------------------------------------------------------


class TestCitationKeyedLookup:
    def test_registered_citation_resolves_to_its_own_predicate(self):
        registry = CitationPredicateRegistry()
        registry.register(SYNTHETIC_CITATION_A, _synthetic_predicate_satisfied)
        requirement = _requirement_with_citation(SYNTHETIC_CITATION_A)

        result = resolve_predicate(fixture_valid_claim(), requirement, registry=registry)

        assert result.outcome is PredicateOutcome.SATISFIED

    def test_two_registered_citations_dispatch_independently(self):
        registry = CitationPredicateRegistry()
        registry.register(SYNTHETIC_CITATION_A, _synthetic_predicate_satisfied)
        registry.register(SYNTHETIC_CITATION_B, _synthetic_predicate_breached)

        req_a = _requirement_with_citation(SYNTHETIC_CITATION_A)
        req_b = _requirement_with_citation(SYNTHETIC_CITATION_B)
        claim = fixture_valid_claim()

        assert resolve_predicate(claim, req_a, registry=registry).outcome is PredicateOutcome.SATISFIED
        assert resolve_predicate(claim, req_b, registry=registry).outcome is PredicateOutcome.BREACHED

    def test_unknown_citation_resolves_to_indeterminate(self):
        registry = CitationPredicateRegistry()
        registry.register(SYNTHETIC_CITATION_A, _synthetic_predicate_satisfied)
        requirement = _requirement_with_citation(SYNTHETIC_CITATION_UNREGISTERED)

        result = resolve_predicate(fixture_valid_claim(), requirement, registry=registry)

        assert result.outcome is PredicateOutcome.INDETERMINATE
        assert result.rationale.strip()
        assert result.detail["unresolved_citation"] == SYNTHETIC_CITATION_UNREGISTERED

    def test_registry_resolve_of_none_citation_is_none_not_a_crash(self):
        registry = CitationPredicateRegistry()
        registry.register(SYNTHETIC_CITATION_A, _synthetic_predicate_satisfied)

        assert registry.resolve(None) is None

    def test_empty_registry_resolves_everything_to_indeterminate(self):
        registry = CitationPredicateRegistry()
        requirement = _requirement_with_citation(SYNTHETIC_CITATION_A)

        result = resolve_predicate(fixture_valid_claim(), requirement, registry=registry)

        assert result.outcome is PredicateOutcome.INDETERMINATE

    def test_register_rejects_empty_citation(self):
        registry = CitationPredicateRegistry()
        try:
            registry.register("   ", _synthetic_predicate_satisfied)
            assert False, "expected ValueError"
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Mapping compatibility with evaluator.py, unmodified
# ---------------------------------------------------------------------------


class TestMappingCompatibilityWithEvaluator:
    def test_wildcard_mapping_dispatches_by_citation_not_by_requirement_id(self):
        registry = CitationPredicateRegistry()
        registry.register(SYNTHETIC_CITATION_A, _synthetic_predicate_satisfied)
        mapping = registry.as_mapping()
        requirement = _requirement_with_citation(SYNTHETIC_CITATION_A, requirement_id="req-aaaa")
        claim = fixture_valid_claim()

        # Any requirement_id-shaped key -- including one never seen before --
        # must resolve to a usable dispatcher.
        predicate_from_real_id = mapping.get(requirement.requirement_id)
        predicate_from_other_id = mapping.get("some-other-random-uuid-like-string")

        assert predicate_from_real_id is not None
        assert predicate_from_other_id is not None
        assert predicate_from_real_id(claim, requirement).outcome is PredicateOutcome.SATISFIED
        assert predicate_from_other_id(claim, requirement).outcome is PredicateOutcome.SATISFIED

    def test_mapping_is_always_truthy_even_when_registry_is_empty(self):
        registry = CitationPredicateRegistry()
        mapping = registry.as_mapping()

        assert bool(mapping) is True
        assert len(mapping) == 0
        # The construct run_evaluation() itself uses: approved_predicates or {}
        assert (mapping or {}) is mapping

    def test_full_compatibility_via_evaluators_own_private_evaluate_predicate(self):
        registry = CitationPredicateRegistry()
        registry.register(SYNTHETIC_CITATION_A, _synthetic_predicate_satisfied)
        mapping = registry.as_mapping()
        requirement = _requirement_with_citation(SYNTHETIC_CITATION_A)
        claim = fixture_valid_claim()

        verdict, rationale, detail, citation, refs = _evaluate_predicate(claim, requirement, mapping)

        assert verdict is Verdict.COMPLIANT
        assert detail["evaluation_path"] == "predicate_satisfied"
        assert rationale.strip()
        assert citation == SYNTHETIC_CITATION_A
        assert refs

    def test_unregistered_citation_via_evaluator_is_needs_review_not_a_crash(self):
        registry = CitationPredicateRegistry()  # empty on purpose
        mapping = registry.as_mapping()
        requirement = _requirement_with_citation(SYNTHETIC_CITATION_UNREGISTERED)
        claim = fixture_valid_claim()

        verdict, rationale, detail, citation, refs = _evaluate_predicate(claim, requirement, mapping)

        assert verdict is Verdict.NEEDS_REVIEW
        assert detail["evaluation_path"] == "predicate_indeterminate"
        assert rationale.strip()

    def test_breached_citation_via_evaluator_is_non_compliant(self):
        registry = CitationPredicateRegistry()
        registry.register(SYNTHETIC_CITATION_B, _synthetic_predicate_breached)
        mapping = registry.as_mapping()
        requirement = _requirement_with_citation(SYNTHETIC_CITATION_B)
        claim = fixture_valid_claim()

        verdict, rationale, detail, citation, refs = _evaluate_predicate(claim, requirement, mapping)

        assert verdict is Verdict.NON_COMPLIANT
        assert detail["evaluation_path"] == "predicate_breached"


# ---------------------------------------------------------------------------
# No heuristic / keyword / text-similarity matching
# ---------------------------------------------------------------------------


class TestNoHeuristicMatchingCanProduceAConclusiveResult:
    def test_near_miss_citation_text_does_not_dispatch(self):
        registry = CitationPredicateRegistry()
        registry.register(SYNTHETIC_CITATION_A, _synthetic_predicate_satisfied)
        near_miss = SYNTHETIC_CITATION_A + " (revised)"
        requirement = _requirement_with_citation(near_miss)

        result = resolve_predicate(fixture_valid_claim(), requirement, registry=registry)

        assert result.outcome is PredicateOutcome.INDETERMINATE

    def test_shared_keywords_do_not_cause_cross_dispatch(self):
        registry = CitationPredicateRegistry()
        registry.register("[SYNTHETIC TEST DATA] container closure integrity A", _synthetic_predicate_satisfied)
        # Shares every keyword with the registered citation, but is not an
        # exact match.
        requirement = _requirement_with_citation("[SYNTHETIC TEST DATA] container closure integrity B")

        result = resolve_predicate(fixture_valid_claim(), requirement, registry=registry)

        assert result.outcome is PredicateOutcome.INDETERMINATE

    def test_resolve_predicate_never_reads_requirement_or_statement_text(self):
        source = inspect.getsource(resolve_predicate)
        assert "requirement.text" not in source
        assert "primary_statement" not in source
        assert "statement_text" not in source
        assert ".text" not in source

    def test_registry_lookup_is_a_single_dict_get_not_a_scan(self):
        source = inspect.getsource(CitationPredicateRegistry.resolve)
        # Exact dict lookup only -- no loop and no substring/fuzzy-match
        # helper anywhere in the lookup implementation.
        assert "for " not in source
        assert "startswith" not in source
        assert "endswith" not in source
        assert "difflib" not in source
        assert ".get(" in source


# ---------------------------------------------------------------------------
# Synthetic labelling / no production content
# ---------------------------------------------------------------------------


class TestSyntheticLabellingAndNoProductionContent:
    def test_test_citations_are_labelled_synthetic(self):
        assert SYNTHETIC_CITATION_A.startswith("[SYNTHETIC TEST DATA]")
        assert SYNTHETIC_CITATION_B.startswith("[SYNTHETIC TEST DATA]")
        assert SYNTHETIC_CITATION_UNREGISTERED.startswith("[SYNTHETIC TEST DATA]")

    def test_test_predicate_rationales_are_labelled_synthetic(self):
        claim = fixture_valid_claim()
        requirement = _requirement_with_citation(SYNTHETIC_CITATION_A)
        result = _synthetic_predicate_satisfied(claim, requirement)
        assert "[SYNTHETIC TEST DATA]" in result.rationale

    def test_production_module_registers_nothing_by_default(self):
        registry = CitationPredicateRegistry()
        assert len(registry) == 0
        assert registry.citations() == frozenset()
        assert registry.resolve("anything at all") is None
