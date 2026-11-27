"""
Tests for src/container_closure/evaluator.py -- Phase 4c.

Group map:
  TestRegulatoryQuestionConstruction   -- dataclass field-ordering fix
  TestInterpretedRequirementConstruction -- dataclass field-ordering fix
  TestPassageInterpreterValidation     -- empty/string/bytes/bytearray/
                                           bad-span/mixed/exception results
  TestRequirementEvidenceLinkerValidation -- primary-exclusion, pool
                                           membership, duplicates,
                                           exceptions/invalid results
  TestSourceRestriction                -- missing/invalid/verified/
                                           mixed verifier results,
                                           fail-closed default
  TestPredicateEvaluation              -- six-row decision table incl.
                                           boundary/applicability
                                           safeguards
  TestSeverityPolicy                   -- required, exception/wrong-type/
                                           inconsistency -> SeverityPolicyError
  TestClaimRollupAndFindings           -- requirement-level findings,
                                           claim-level roll-up
  TestRetrievalLedger                  -- completeness, provenance,
                                           JSON-safe serialization
  TestAuditPersistence                 -- durable ledger persistence,
                                           audit-write failure behaviour
  TestCrossSectionBoundary             -- S7 never independently produces
                                           a regulatory finding

All data is synthetic.
"""
from __future__ import annotations

import pytest

from container_closure.evaluator import (
    ApplicabilityConfidence,
    EvaluatorRunAborted,
    InterpretedRequirement,
    PassageInterpretation,
    PassageStatement,
    PredicateAssessment,
    PredicateOutcome,
    RegulatoryQuestion,
    RetrievedPassage,
    SeverityPolicyError,
    SourceVerificationStatus,
    _classify_applicability,
    _evaluate_predicate,
    _interpret_passage,
    _link_supporting_statements,
    _verify_source_restriction,
    run_evaluation,
)
from container_closure.ports import PortError
from shared.enums import EventStatus, FindingType, Severity, Verdict
from shared.query import get_session_events, get_session_findings

from tests.fixtures.score_fixtures import fixture_invalid_raw_claim_input

from tests.fixtures.evaluator_fixtures import (
    MockEvidenceSource,
    fixture_interpreted_requirement,
    fixture_passage,
    fixture_question,
    fixture_statement,
    make_inconsistent_severity_policy,
    synthetic_applicability_directly_relevant,
    synthetic_applicability_invalid_result,
    synthetic_applicability_uncertain,
    synthetic_empty_question_builder,
    synthetic_interpreter_bad_span,
    synthetic_interpreter_empty,
    synthetic_interpreter_mixed_valid_invalid,
    synthetic_interpreter_not_applicable,
    synthetic_interpreter_out_of_bounds_span,
    synthetic_interpreter_requirement,
    synthetic_interpreter_returns_bytearray,
    synthetic_interpreter_returns_bytes,
    synthetic_interpreter_returns_string,
    synthetic_interpreter_supporting,
    synthetic_linker_returns_duplicates,
    synthetic_linker_returns_foreign,
    synthetic_linker_returns_pool,
    synthetic_linker_returns_primary,
    synthetic_predicate_breached,
    synthetic_predicate_indeterminate,
    synthetic_predicate_invalid_result,
    synthetic_predicate_missing_rationale,
    synthetic_predicate_satisfied,
    synthetic_predicate_satisfied_no_evidence,
    synthetic_question_builder,
    synthetic_raising_applicability_classifier,
    synthetic_raising_interpreter,
    synthetic_raising_linker,
    synthetic_raising_predicate,
    synthetic_raising_question_builder,
    synthetic_raising_severity_policy,
    synthetic_raising_verifier,
    synthetic_severity_policy,
    synthetic_severity_policy_wrong_type,
    synthetic_verify_all,
    synthetic_verify_extra_key,
    synthetic_verify_invalid_value,
    synthetic_verify_mixed,
    synthetic_verify_missing_key,
    synthetic_verify_none,
)
from tests.fixtures.s6_fixtures import (
    MockClaimSource,
    MockStabilitySource,
    fixture_claim_bad_source_ref_no_type,
    fixture_claim_empty_id,
    fixture_claim_empty_text,
    fixture_claim_wrong_section,
    fixture_source_ref,
    fixture_valid_claim,
)


# ---------------------------------------------------------------------------
# Dataclass construction (final corrections)
# ---------------------------------------------------------------------------


class TestRegulatoryQuestionConstruction:
    def test_valid_construction_with_only_the_required_field(self) -> None:
        q = RegulatoryQuestion(question="[SYNTHETIC] Does this comply?")
        assert q.question == "[SYNTHETIC] Does this comply?"
        assert q.ctd_sections == ("3.2.S.6",)
        assert isinstance(q.question_id, str) and q.question_id

    def test_two_questions_get_distinct_stable_ids(self) -> None:
        q1 = RegulatoryQuestion(question="a")
        q2 = RegulatoryQuestion(question="a")
        assert q1.question_id != q2.question_id


class TestInterpretedRequirementConstruction:
    def test_valid_construction_with_required_fields_only(self) -> None:
        stmt = fixture_statement()
        req = InterpretedRequirement(
            requirement_id="req-1",
            text=stmt.statement_text,
            citation="[SYNTHETIC] citation",
            primary_statement=stmt,
            applicability=ApplicabilityConfidence.DIRECTLY_RELEVANT,
        )
        assert req.requirement_id == "req-1"
        assert req.supporting_statements == ()
        assert req.detail == {}


# ---------------------------------------------------------------------------
# PassageInterpreter validation
# ---------------------------------------------------------------------------


class TestPassageInterpreterValidation:
    def test_empty_sequence_falls_back_to_uncertain_and_is_not_dropped(self) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        stmts, detail = _interpret_passage(passage, claim, synthetic_interpreter_empty)
        assert len(stmts) == 1
        assert stmts[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION
        assert stmts[0].boundary_confidence == "uncertain"
        assert detail["evaluation_path"] == "passage_interpreter_empty_result"

    def test_string_result_is_rejected(self) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        stmts, detail = _interpret_passage(passage, claim, synthetic_interpreter_returns_string)
        assert len(stmts) == 1
        assert stmts[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION
        assert detail["evaluation_path"] == "passage_interpreter_invalid_result"

    def test_bytes_result_is_rejected(self) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        stmts, detail = _interpret_passage(passage, claim, synthetic_interpreter_returns_bytes)
        assert len(stmts) == 1
        assert stmts[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION
        assert detail["evaluation_path"] == "passage_interpreter_invalid_result"

    def test_bytearray_result_is_rejected(self) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        stmts, detail = _interpret_passage(passage, claim, synthetic_interpreter_returns_bytearray)
        assert len(stmts) == 1
        assert stmts[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION
        assert detail["evaluation_path"] == "passage_interpreter_invalid_result"

    def test_invalid_substring_is_rejected(self) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()

        def bad_interpreter(p, c):  # noqa: ARG001
            return [
                PassageStatement(
                    statement_text="definitely not in the passage text",
                    source_passage=p,
                    interpretation=PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT,
                    boundary_confidence="confident",
                    span=None,
                )
            ]

        stmts, detail = _interpret_passage(passage, claim, bad_interpreter)
        assert len(stmts) == 1
        assert stmts[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION
        assert detail["evaluation_path"] == "passage_interpreter_invalid_result"

    def test_span_text_mismatch_is_rejected(self) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        stmts, detail = _interpret_passage(passage, claim, synthetic_interpreter_bad_span)
        assert len(stmts) == 1
        assert stmts[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION
        assert detail["evaluation_path"] == "passage_interpreter_invalid_result"

    def test_out_of_bounds_span_is_rejected(self) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        stmts, detail = _interpret_passage(passage, claim, synthetic_interpreter_out_of_bounds_span)
        assert len(stmts) == 1
        assert stmts[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION
        assert detail["evaluation_path"] == "passage_interpreter_invalid_result"

    def test_mixed_valid_and_invalid_statements_keeps_the_valid_one(self) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        stmts, detail = _interpret_passage(passage, claim, synthetic_interpreter_mixed_valid_invalid)
        assert len(stmts) == 1
        assert stmts[0].interpretation == PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT
        assert detail["evaluation_path"] == "passage_interpreted"
        assert "rejected_statements" in detail

    def test_exception_falls_back_to_uncertain(self) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        stmts, detail = _interpret_passage(passage, claim, synthetic_raising_interpreter)
        assert len(stmts) == 1
        assert stmts[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION
        assert detail["evaluation_path"] == "passage_interpreter_error"

    def test_no_interpreter_supplied_falls_back_to_uncertain(self) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        stmts, detail = _interpret_passage(passage, claim, None)
        assert len(stmts) == 1
        assert stmts[0].interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION
        assert detail["evaluation_path"] == "no_passage_interpreter"

    def test_valid_requirement_classification_passes_through(self) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        stmts, detail = _interpret_passage(passage, claim, synthetic_interpreter_requirement)
        assert len(stmts) == 1
        assert stmts[0].interpretation == PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT
        assert detail["evaluation_path"] == "passage_interpreted"

    def test_valid_not_applicable_classification_passes_through(self) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        stmts, _ = _interpret_passage(passage, claim, synthetic_interpreter_not_applicable)
        assert stmts[0].interpretation == PassageInterpretation.NOT_APPLICABLE


# ---------------------------------------------------------------------------
# RequirementEvidenceLinker validation
# ---------------------------------------------------------------------------


class TestRequirementEvidenceLinkerValidation:
    def test_no_linker_yields_no_supporting_statements(self) -> None:
        primary = fixture_statement()
        supporting, detail = _link_supporting_statements(primary, [], None)
        assert supporting == ()
        assert detail == {}

    def test_primary_cannot_appear_as_its_own_supporting_statement(self) -> None:
        passage = fixture_passage()
        primary = fixture_statement(passage=passage, interpretation=PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT)
        other = fixture_statement(passage=fixture_passage(passage_id="other"), interpretation=PassageInterpretation.SUPPORTING_INFORMATION)
        pool = [primary, other]
        supporting, detail = _link_supporting_statements(primary, pool, synthetic_linker_returns_primary)
        assert supporting == ()
        assert detail["linker_dropped"][0]["reason"] == "linker_excluded_primary_as_supporting"

    def test_candidate_not_in_pool_is_dropped(self) -> None:
        primary = fixture_statement()
        pool = [fixture_statement(passage=fixture_passage(passage_id="p2"))]
        supporting, detail = _link_supporting_statements(primary, pool, synthetic_linker_returns_foreign)
        assert supporting == ()
        assert detail["linker_dropped"][0]["reason"] == "linker_candidate_not_in_pool"

    def test_duplicate_supporting_statements_are_deduplicated(self) -> None:
        passage = fixture_passage(passage_id="p2")
        primary = fixture_statement()
        other = fixture_statement(passage=passage, interpretation=PassageInterpretation.SUPPORTING_INFORMATION)
        pool = [other]
        supporting, detail = _link_supporting_statements(primary, pool, synthetic_linker_returns_duplicates)
        assert len(supporting) == 1
        assert detail["linker_dropped"][0]["reason"] == "linker_duplicate_candidate"

    def test_valid_pool_subset_is_accepted(self) -> None:
        primary = fixture_statement()
        other = fixture_statement(passage=fixture_passage(passage_id="p2"), interpretation=PassageInterpretation.SUPPORTING_INFORMATION)
        pool = [other]
        supporting, detail = _link_supporting_statements(primary, pool, synthetic_linker_returns_pool)
        assert supporting == (other,)
        assert "linker_dropped" not in detail

    def test_linker_exception_yields_no_supporting_statements(self) -> None:
        primary = fixture_statement()
        supporting, detail = _link_supporting_statements(primary, [], synthetic_raising_linker)
        assert supporting == ()
        assert detail["linker_evaluation_path"] == "linker_error"

    def test_linker_invalid_result_type_yields_no_supporting_statements(self) -> None:
        primary = fixture_statement()

        def bad_linker(p, pool):  # noqa: ARG001
            return "not a sequence of statements"

        supporting, detail = _link_supporting_statements(primary, [], bad_linker)
        assert supporting == ()
        assert detail["linker_evaluation_path"] == "linker_invalid_result"


# ---------------------------------------------------------------------------
# Source restriction (fail-closed gate)
# ---------------------------------------------------------------------------


class TestSourceRestriction:
    def test_no_verifier_fails_closed_for_every_passage(self) -> None:
        passages = [fixture_passage(passage_id="a"), fixture_passage(passage_id="b")]
        dispositions, detail = _verify_source_restriction(passages, None)
        assert all(v == SourceVerificationStatus.UNVERIFIABLE for v in dispositions.values())
        assert detail["evaluation_path"] == "source_restriction_unverifiable_no_verifier"

    def test_verifier_exception_fails_closed(self) -> None:
        passages = [fixture_passage(passage_id="a")]
        dispositions, detail = _verify_source_restriction(passages, synthetic_raising_verifier)
        assert dispositions["a"] == SourceVerificationStatus.UNVERIFIABLE
        assert detail["evaluation_path"] == "source_restriction_verifier_error"

    def test_verifier_missing_key_is_invalid_and_fails_closed(self) -> None:
        passages = [fixture_passage(passage_id="a"), fixture_passage(passage_id="b")]
        dispositions, detail = _verify_source_restriction(passages, synthetic_verify_missing_key)
        assert all(v == SourceVerificationStatus.UNVERIFIABLE for v in dispositions.values())
        assert detail["evaluation_path"] == "source_restriction_verifier_invalid_result"

    def test_verifier_extra_key_is_invalid_and_fails_closed(self) -> None:
        passages = [fixture_passage(passage_id="a")]
        dispositions, detail = _verify_source_restriction(passages, synthetic_verify_extra_key)
        assert dispositions["a"] == SourceVerificationStatus.UNVERIFIABLE
        assert detail["evaluation_path"] == "source_restriction_verifier_invalid_result"

    def test_verifier_non_enum_value_is_invalid_and_fails_closed(self) -> None:
        passages = [fixture_passage(passage_id="a")]
        dispositions, detail = _verify_source_restriction(passages, synthetic_verify_invalid_value)
        assert dispositions["a"] == SourceVerificationStatus.UNVERIFIABLE
        assert detail["evaluation_path"] == "source_restriction_verifier_invalid_result"

    def test_fully_verified_result_is_exact(self) -> None:
        passages = [fixture_passage(passage_id="a"), fixture_passage(passage_id="b")]
        dispositions, detail = _verify_source_restriction(passages, synthetic_verify_all)
        assert all(v == SourceVerificationStatus.VERIFIED for v in dispositions.values())
        assert detail["evaluation_path"] == "source_restriction_fully_verified"
        assert detail["passages_verified"] == 2

    def test_none_verified_result_is_distinct_from_no_verifier(self) -> None:
        passages = [fixture_passage(passage_id="a")]
        dispositions, detail = _verify_source_restriction(passages, synthetic_verify_none)
        assert dispositions["a"] == SourceVerificationStatus.UNVERIFIABLE
        assert detail["evaluation_path"] == "source_restriction_none_verified"

    def test_partial_verification_never_implies_full_verification(self) -> None:
        passages = [fixture_passage(passage_id="a"), fixture_passage(passage_id="b")]
        dispositions, detail = _verify_source_restriction(passages, synthetic_verify_mixed)
        assert dispositions["a"] == SourceVerificationStatus.VERIFIED
        assert dispositions["b"] == SourceVerificationStatus.CONFIRMED_OUTSIDE_SCOPE
        assert detail["evaluation_path"] == "source_restriction_partially_verified"
        assert detail["passages_verified"] == 1
        assert detail["passages_considered"] == 2


# ---------------------------------------------------------------------------
# Predicate evaluation
# ---------------------------------------------------------------------------


class TestPredicateEvaluation:
    def test_no_predicate_registered_yields_needs_review(self) -> None:
        claim = fixture_valid_claim()
        req = fixture_interpreted_requirement(requirement_id="req-x")
        verdict, _, detail, _, _ = _evaluate_predicate(claim, req, {})
        assert verdict == Verdict.NEEDS_REVIEW
        assert detail["evaluation_path"] == "no_predicate"

    def test_predicate_exception_yields_needs_review(self) -> None:
        claim = fixture_valid_claim()
        req = fixture_interpreted_requirement(requirement_id="req-x")
        verdict, _, detail, _, _ = _evaluate_predicate(claim, req, {"req-x": synthetic_raising_predicate})
        assert verdict == Verdict.NEEDS_REVIEW
        assert detail["evaluation_path"] == "predicate_error"

    def test_predicate_invalid_result_yields_needs_review(self) -> None:
        claim = fixture_valid_claim()
        req = fixture_interpreted_requirement(requirement_id="req-x")
        verdict, _, detail, _, _ = _evaluate_predicate(claim, req, {"req-x": synthetic_predicate_invalid_result})
        assert verdict == Verdict.NEEDS_REVIEW
        assert detail["evaluation_path"] == "predicate_invalid_result"

    def test_predicate_missing_rationale_yields_needs_review(self) -> None:
        claim = fixture_valid_claim()
        req = fixture_interpreted_requirement(requirement_id="req-x")
        verdict, _, detail, _, _ = _evaluate_predicate(claim, req, {"req-x": synthetic_predicate_missing_rationale})
        assert verdict == Verdict.NEEDS_REVIEW
        assert detail["invalid_reason"] == "missing_rationale"

    def test_predicate_indeterminate_yields_needs_review(self) -> None:
        claim = fixture_valid_claim()
        req = fixture_interpreted_requirement(requirement_id="req-x")
        verdict, _, detail, _, _ = _evaluate_predicate(claim, req, {"req-x": synthetic_predicate_indeterminate})
        assert verdict == Verdict.NEEDS_REVIEW
        assert detail["evaluation_path"] == "predicate_indeterminate"

    def test_satisfied_without_evidence_yields_needs_review_not_compliant(self) -> None:
        claim = fixture_valid_claim()
        req = fixture_interpreted_requirement(requirement_id="req-x")
        verdict, _, detail, _, _ = _evaluate_predicate(claim, req, {"req-x": synthetic_predicate_satisfied_no_evidence})
        assert verdict == Verdict.NEEDS_REVIEW
        assert detail["evaluation_path"] == "predicate_missing_evidence"

    def test_satisfied_with_evidence_yields_compliant(self) -> None:
        claim = fixture_valid_claim()
        req = fixture_interpreted_requirement(requirement_id="req-x")
        verdict, _, detail, citation, refs = _evaluate_predicate(claim, req, {"req-x": synthetic_predicate_satisfied})
        assert verdict == Verdict.COMPLIANT
        assert detail["evaluation_path"] == "predicate_satisfied"
        assert citation
        assert len(refs) >= 2

    def test_breached_with_evidence_yields_non_compliant(self) -> None:
        claim = fixture_valid_claim()
        req = fixture_interpreted_requirement(requirement_id="req-x")
        verdict, _, detail, _, _ = _evaluate_predicate(claim, req, {"req-x": synthetic_predicate_breached})
        assert verdict == Verdict.NON_COMPLIANT
        assert detail["evaluation_path"] == "predicate_breached"

    def test_uncertain_applicability_downgrades_satisfied_to_needs_review(self) -> None:
        claim = fixture_valid_claim()
        req = fixture_interpreted_requirement(
            requirement_id="req-x", applicability=ApplicabilityConfidence.UNCERTAIN
        )
        verdict, _, detail, _, _ = _evaluate_predicate(claim, req, {"req-x": synthetic_predicate_satisfied})
        assert verdict == Verdict.NEEDS_REVIEW
        assert detail["evaluation_path"] == "predicate_satisfied_without_evidence"

    def test_uncertain_boundary_downgrades_breached_to_needs_review(self) -> None:
        claim = fixture_valid_claim()
        passage = fixture_passage()
        stmt = fixture_statement(passage=passage, boundary_confidence="uncertain")
        req = fixture_interpreted_requirement(requirement_id="req-x", statement=stmt)
        verdict, _, detail, _, _ = _evaluate_predicate(claim, req, {"req-x": synthetic_predicate_breached})
        assert verdict == Verdict.NEEDS_REVIEW
        assert detail["evaluation_path"] == "requirement_boundary_uncertain"


# ---------------------------------------------------------------------------
# Applicability classifier validation (used by run_evaluation internals)
# ---------------------------------------------------------------------------


class TestApplicabilityClassifierValidation:
    def test_no_classifier_defaults_to_uncertain(self) -> None:
        confidence, detail = _classify_applicability(fixture_passage(), fixture_valid_claim(), None)
        assert confidence == ApplicabilityConfidence.UNCERTAIN
        assert detail["evaluation_path"] == "no_applicability_classifier"

    def test_exception_defaults_to_uncertain(self) -> None:
        confidence, detail = _classify_applicability(
            fixture_passage(), fixture_valid_claim(), synthetic_raising_applicability_classifier
        )
        assert confidence == ApplicabilityConfidence.UNCERTAIN
        assert detail["evaluation_path"] == "applicability_classifier_error"

    def test_invalid_result_defaults_to_uncertain(self) -> None:
        confidence, detail = _classify_applicability(
            fixture_passage(), fixture_valid_claim(), synthetic_applicability_invalid_result
        )
        assert confidence == ApplicabilityConfidence.UNCERTAIN
        assert detail["evaluation_path"] == "applicability_classifier_invalid_result"

    def test_valid_result_passes_through(self) -> None:
        confidence, detail = _classify_applicability(
            fixture_passage(), fixture_valid_claim(), synthetic_applicability_directly_relevant
        )
        assert confidence == ApplicabilityConfidence.DIRECTLY_RELEVANT
        assert detail == {}


# ---------------------------------------------------------------------------
# Severity policy -- required, never silently substituted
# ---------------------------------------------------------------------------


class TestSeverityPolicy:
    def _run(self, memory_engine, severity_policy):
        claim = fixture_valid_claim()
        return run_evaluation(
            memory_engine,
            session_id="sess-sev",
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource([]),
            severity_policy=severity_policy,
        )

    def test_raising_policy_aborts_the_run(self, memory_engine) -> None:
        with pytest.raises(SeverityPolicyError):
            self._run(memory_engine, synthetic_raising_severity_policy)

    def test_wrong_type_policy_aborts_the_run(self, memory_engine) -> None:
        with pytest.raises(SeverityPolicyError):
            self._run(memory_engine, synthetic_severity_policy_wrong_type)

    def test_inconsistent_policy_aborts_the_run(self, memory_engine) -> None:
        claim_a = fixture_valid_claim(claim_id="c-a")
        claim_b = fixture_valid_claim(claim_id="c-b")
        policy = make_inconsistent_severity_policy()
        with pytest.raises(SeverityPolicyError):
            run_evaluation(
                memory_engine,
                session_id="sess-sev-2",
                claim_source=MockClaimSource([claim_a, claim_b]),
                stability_source=MockStabilitySource([]),
                severity_policy=policy,
            )

    def test_valid_policy_succeeds(self, memory_engine) -> None:
        result = self._run(memory_engine, synthetic_severity_policy)
        assert result.regulatory[0].assessments[0].severity == Severity.MINOR


# ---------------------------------------------------------------------------
# Claim-level roll-up and findings
# ---------------------------------------------------------------------------


class TestClaimRollupAndFindings:
    def test_no_question_builder_yields_insufficient_data(self, memory_engine) -> None:
        claim = fixture_valid_claim()
        result = run_evaluation(
            memory_engine,
            session_id="sess-1",
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
        )
        assert len(result.regulatory) == 1
        assert result.regulatory[0].overall_verdict == Verdict.INSUFFICIENT_DATA
        assert result.regulatory[0].assessments[0].detail["evaluation_path"] == "no_question_builder"

    def test_assessments_is_never_empty(self, memory_engine) -> None:
        claim = fixture_valid_claim()
        result = run_evaluation(
            memory_engine,
            session_id="sess-2",
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
            question_builder=synthetic_empty_question_builder,
            evidence_source=MockEvidenceSource([]),
        )
        assert len(result.regulatory[0].assessments) >= 1
        assert result.regulatory[0].assessments[0].detail["evaluation_path"] == "no_topics_selected"

    def test_requirement_port_unavailable_is_insufficient_data(self, memory_engine) -> None:
        claim = fixture_valid_claim()
        result = run_evaluation(
            memory_engine,
            session_id="sess-3",
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
            question_builder=synthetic_question_builder,
            evidence_source=MockEvidenceSource(raise_port_error=True),
        )
        assert result.regulatory[0].overall_verdict == Verdict.INSUFFICIENT_DATA
        assert result.regulatory[0].assessments[0].detail["evaluation_path"] == "requirement_port_unavailable"

    def test_full_pipeline_compliant_requirement_produces_one_finding(self, memory_engine) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        result = run_evaluation(
            memory_engine,
            session_id="sess-4",
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
            question_builder=synthetic_question_builder,
            evidence_source=MockEvidenceSource([passage]),
            source_restriction_verifier=synthetic_verify_all,
            passage_interpreter=synthetic_interpreter_requirement,
            applicability_classifier=synthetic_applicability_directly_relevant,
            approved_predicates={},  # left empty on purpose: no_predicate -> NEEDS_REVIEW
        )
        claim_result = result.regulatory[0]
        assert len(claim_result.assessments) == 1
        assert claim_result.assessments[0].requirement_id is not None
        assert claim_result.overall_verdict == Verdict.NEEDS_REVIEW
        findings = get_session_findings(memory_engine, "sess-4")
        assert len(findings) == 1
        assert findings[0].finding_type == FindingType.COMPLIANCE

    def test_one_compliant_requirement_never_overrides_an_unresolved_one(self, memory_engine) -> None:
        passage_a = fixture_passage(passage_id="pa")
        passage_b = fixture_passage(passage_id="pb")
        claim = fixture_valid_claim()

        def two_statement_interpreter(p, c):  # noqa: ARG001
            return [fixture_statement(passage=p, interpretation=PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT)]

        requirement_ids: list[str] = []

        def predicate_factory(claim_arg, requirement):
            requirement_ids.append(requirement.requirement_id)
            if len(requirement_ids) == 1:
                return PredicateAssessment(
                    outcome=PredicateOutcome.SATISFIED,
                    rationale="[SYNTHETIC] satisfied",
                    source_refs=(fixture_source_ref(),),
                )
            return PredicateAssessment(outcome=PredicateOutcome.INDETERMINATE, rationale="[SYNTHETIC] unclear")

        class _AnyPredicateMap(dict):
            def get(self, key, default=None):  # noqa: ARG002
                return predicate_factory

            def __bool__(self) -> bool:
                return True  # non-empty so `approved_predicates or {}` keeps this mapping

        result = run_evaluation(
            memory_engine,
            session_id="sess-5",
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
            question_builder=synthetic_question_builder,
            evidence_source=MockEvidenceSource([passage_a, passage_b]),
            source_restriction_verifier=synthetic_verify_all,
            passage_interpreter=two_statement_interpreter,
            applicability_classifier=synthetic_applicability_directly_relevant,
            approved_predicates=_AnyPredicateMap(),
        )
        verdicts = {a.verdict for a in result.regulatory[0].assessments}
        assert Verdict.COMPLIANT in verdicts
        assert Verdict.NEEDS_REVIEW in verdicts
        assert result.regulatory[0].overall_verdict == Verdict.NEEDS_REVIEW


# ---------------------------------------------------------------------------
# Retrieval ledger
# ---------------------------------------------------------------------------


class TestRetrievalLedger:
    def test_unverified_passages_are_recorded_in_ledger(self, memory_engine) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        result = run_evaluation(
            memory_engine,
            session_id="sess-6",
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
            question_builder=synthetic_question_builder,
            evidence_source=MockEvidenceSource([passage]),
        )
        ledger = result.regulatory[0].retrieval_ledger
        assert len(ledger) == 1
        assert ledger[0].verification_status == SourceVerificationStatus.UNVERIFIABLE
        assert ledger[0].passage_id == passage.passage_id

    def test_excluded_passages_are_traceable_without_a_finding(self, memory_engine) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        result = run_evaluation(
            memory_engine,
            session_id="sess-7",
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
            question_builder=synthetic_question_builder,
            evidence_source=MockEvidenceSource([passage]),
            source_restriction_verifier=synthetic_verify_all,
            passage_interpreter=synthetic_interpreter_not_applicable,
        )
        ledger = result.regulatory[0].retrieval_ledger
        assert len(ledger) == 1
        assert ledger[0].verification_status == SourceVerificationStatus.VERIFIED
        assert ledger[0].statements[0].interpretation == PassageInterpretation.NOT_APPLICABLE
        findings = get_session_findings(memory_engine, "sess-7")
        # Confidently-excluded content never produces its own finding; the claim
        # still gets exactly one INSUFFICIENT_DATA sentinel finding.
        assert len(findings) == 1
        assert findings[0].verdict == Verdict.INSUFFICIENT_DATA
        assert findings[0].detail["evaluation_path"] == "no_applicable_requirement_identified"

    def test_ledger_entry_serializes_to_json_safe_structure(self) -> None:
        from container_closure.evaluator import _ledger_entry_to_json, RetrievalLedgerEntry, PassageStatementSummary

        passage = fixture_passage()
        entry = RetrievalLedgerEntry(
            passage_id=passage.passage_id,
            originating_question_id=passage.originating_question_id,
            source_ref=passage.source_ref,
            verification_status=SourceVerificationStatus.VERIFIED,
            statements=(
                PassageStatementSummary(
                    statement_text="x",
                    span=(0, 1),
                    interpretation=PassageInterpretation.NOT_APPLICABLE,
                    boundary_confidence="confident",
                ),
            ),
            detail={"evaluation_path": "passage_interpreted"},
        )
        import json

        payload = _ledger_entry_to_json(entry)
        serialized = json.dumps(payload)  # must not raise
        assert isinstance(serialized, str)
        assert payload["verification_status"] == "verified"
        assert payload["statements"][0]["interpretation"] == "not_applicable"
        assert payload["statements"][0]["span"] == [0, 1]


# ---------------------------------------------------------------------------
# Audit persistence
# ---------------------------------------------------------------------------


class TestAuditPersistence:
    def test_retrieval_ledger_event_is_durably_persisted(self, memory_engine) -> None:
        passage = fixture_passage()
        claim = fixture_valid_claim()
        result = run_evaluation(
            memory_engine,
            session_id="sess-8",
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
            question_builder=synthetic_question_builder,
            evidence_source=MockEvidenceSource([passage]),
        )
        # Independent read, NOT the in-memory result object -- proves durability.
        events = get_session_events(memory_engine, "sess-8")
        ledger_events = [e for e in events if e.action == "retrieval_ledger"]
        assert len(ledger_events) == 1
        assert ledger_events[0].status == EventStatus.COMPLETED
        assert ledger_events[0].parent_event_id == result.event_id
        assert ledger_events[0].detail["claim_id"] == claim.claim_id
        assert ledger_events[0].detail["entries"][0]["passage_id"] == passage.passage_id

    def test_audit_write_failure_aborts_the_run_and_wraps_the_cause(self, memory_engine) -> None:
        claim = fixture_valid_claim()

        class _BrokenClaimSource:
            def get_claims(self, session_id):  # noqa: ARG002
                raise PortError("simulated M3 unavailability")

        with pytest.raises(EvaluatorRunAborted):
            run_evaluation(
                memory_engine,
                session_id="sess-9",
                claim_source=_BrokenClaimSource(),
                stability_source=MockStabilitySource([]),
                severity_policy=synthetic_severity_policy,
            )
        # A started event was written; the run failed before any finding existed.
        events = get_session_events(memory_engine, "sess-9")
        assert any(e.status == EventStatus.STARTED for e in events)
        assert any(e.status == EventStatus.FAILED for e in events)
        assert get_session_findings(memory_engine, "sess-9") == []

    def test_findings_from_earlier_claims_survive_a_later_claim_failure(self, memory_engine) -> None:
        from shared.audit import write_finding as _real_write_finding
        import container_closure.evaluator as ev_module

        claim_a = fixture_valid_claim(claim_id="c-a")
        claim_b = fixture_valid_claim(claim_id="c-b")
        calls = {"n": 0}
        original = ev_module.write_finding

        def flaky_write_finding(engine, finding):
            calls["n"] += 1
            if calls["n"] > 1:
                from shared.exceptions import AuditWriteError

                raise AuditWriteError("simulated database failure")
            return original(engine, finding)

        ev_module.write_finding = flaky_write_finding
        try:
            with pytest.raises(EvaluatorRunAborted):
                run_evaluation(
                    memory_engine,
                    session_id="sess-10",
                    claim_source=MockClaimSource([claim_a, claim_b]),
                    stability_source=MockStabilitySource([]),
                    severity_policy=synthetic_severity_policy,
                )
        finally:
            ev_module.write_finding = original

        findings = get_session_findings(memory_engine, "sess-10")
        # claim_a's finding (written before the simulated failure) is still there.
        assert len(findings) == 1
        assert findings[0].claim_id == "c-a"


# ---------------------------------------------------------------------------
# Cross-section boundary
# ---------------------------------------------------------------------------


class TestCrossSectionBoundary:
    def test_s7_information_never_produces_a_contradiction_finding(self, memory_engine) -> None:
        claim = fixture_valid_claim(claim_id="c-stability")
        result = run_evaluation(
            memory_engine,
            session_id="sess-11",
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
        )
        assert result.cross_section_status == "ok"
        assert result.cross_section is not None
        findings = get_session_findings(memory_engine, "sess-11")
        assert all(f.finding_type == FindingType.COMPLIANCE for f in findings)

    def test_stability_port_failure_does_not_affect_regulatory_assessment(self, memory_engine) -> None:
        claim = fixture_valid_claim()
        result = run_evaluation(
            memory_engine,
            session_id="sess-12",
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource(raise_port_error=True),
            severity_policy=synthetic_severity_policy,
            question_builder=synthetic_question_builder,
        )
        assert result.cross_section_status == "port_unavailable"
        assert result.cross_section is None
        # Regulatory evaluation still ran normally for the claim.
        assert len(result.regulatory) == 1


# ---------------------------------------------------------------------------
# Phase 5a: parser integration
# ---------------------------------------------------------------------------


class TestParserIntegration:
    """container_closure.parser.parse_claims() is now called inside
    run_evaluation() before any claim reaches the regulatory pipeline.
    These tests cover the integration itself; tests/test_evaluator_integration.py
    covers the full multi-reason, multi-claim scenarios and audit-record
    shape in more depth."""

    def test_accepted_claim_still_evaluated_normally(self, memory_engine) -> None:
        """A structurally valid claim's behaviour is unchanged by the
        parser-integration edit."""
        claim = fixture_valid_claim(claim_id="c-parser-ok")
        result = run_evaluation(
            memory_engine,
            session_id="sess-parser-1",
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
        )
        assert len(result.regulatory) == 1
        assert result.regulatory[0].claim_id == "c-parser-ok"

    def test_structurally_rejected_claim_is_excluded_from_regulatory_pipeline(self, memory_engine) -> None:
        result = run_evaluation(
            memory_engine,
            session_id="sess-parser-2",
            claim_source=MockClaimSource([fixture_claim_wrong_section()]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
        )
        assert result.regulatory == []

    def test_empty_claim_id_rejection_writes_event_not_finding(self, memory_engine) -> None:
        """An empty claim_id is not a validated, usable identifier, so
        this must never produce a FindingRecord (not even one with
        claim_id=None) -- only a plain AuditEvent, exactly like
        invalid_input."""
        result = run_evaluation(
            memory_engine,
            session_id="sess-parser-3",
            claim_source=MockClaimSource([fixture_claim_empty_id()]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
        )
        assert get_session_findings(memory_engine, "sess-parser-3") == []
        events = get_session_events(memory_engine, "sess-parser-3")
        rejected = [e for e in events if e.action == "s6_claim_rejected_empty_claim_id"]
        assert len(rejected) == 1
        assert rejected[0].parent_event_id == result.event_id
        assert rejected[0].status == EventStatus.COMPLETED

    def test_genuinely_validated_claim_id_is_carried_through(self, memory_engine) -> None:
        run_evaluation(
            memory_engine,
            session_id="sess-parser-4",
            claim_source=MockClaimSource([fixture_claim_empty_text()]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
        )
        findings = get_session_findings(memory_engine, "sess-parser-4")
        assert len(findings) == 1
        assert findings[0].claim_id == "c-empty-text"

    def test_bad_source_ref_rejection_is_audited(self, memory_engine) -> None:
        run_evaluation(
            memory_engine,
            session_id="sess-parser-5",
            claim_source=MockClaimSource([fixture_claim_bad_source_ref_no_type()]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
        )
        findings = get_session_findings(memory_engine, "sess-parser-5")
        assert len(findings) == 1
        assert findings[0].detail["evaluation_path"] == "claim_rejected_invalid_source_ref"

    def test_invalid_input_writes_event_not_finding(self, memory_engine) -> None:
        result = run_evaluation(
            memory_engine,
            session_id="sess-parser-6",
            claim_source=MockClaimSource([fixture_invalid_raw_claim_input()]),  # type: ignore[list-item]
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
        )
        assert get_session_findings(memory_engine, "sess-parser-6") == []
        events = get_session_events(memory_engine, "sess-parser-6")
        rejected = [e for e in events if e.action == "s6_claim_rejected_invalid_input"]
        assert len(rejected) == 1
        assert rejected[0].parent_event_id == result.event_id
        assert rejected[0].status == EventStatus.COMPLETED
