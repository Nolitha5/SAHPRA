"""
Phase 5a integration tests for container_closure.evaluator.run_evaluation.

Two things are new here relative to tests/test_evaluator.py (Phase 4c):

1. A full, end-to-end "happy path" run exercising every extension point
   at once via the existing Phase 4c synthetic fixtures
   (tests/fixtures/evaluator_fixtures.py). This is MECHANISM VERIFICATION
   ONLY: it proves the pipeline composes correctly (claim -> question ->
   retrieval -> source verification -> interpretation -> linking ->
   predicate -> severity -> roll-up -> persisted finding + ledger). The
   synthetic verifier, interpreter, and predicate used here are test-only
   stand-ins with no connection to any real M2 category mapping or any
   pharmacist-approved regulatory rule; the COMPLIANT verdict this run
   produces is NOT a real regulatory conclusion and must never be read
   as one. Production code must never wire these synthetic fixtures into
   a real evaluation run.

2. Tests for the Phase 5a parser-integration change: every one of
   parser.parse_claims's five rejection reasons is exercised through
   run_evaluation itself (not just parser.parse_claims in isolation),
   confirming the correct audit artifact (FindingRecord vs. plain
   AuditEvent) is produced for each, with no claim_id ever fabricated.
"""
from __future__ import annotations

from shared.enums import AgentName, EventStatus, Verdict
from shared.query import get_session_events, get_session_findings

from container_closure.evaluator import run_evaluation
from container_closure.ports import PortError

from tests.fixtures.evaluator_fixtures import (
    MockEvidenceSource,
    fixture_passage,
    synthetic_applicability_directly_relevant,
    synthetic_interpreter_requirement,
    synthetic_linker_none,
    synthetic_predicate_satisfied,
    synthetic_question_builder,
    synthetic_severity_policy,
    synthetic_verify_all,
)
from tests.fixtures.s6_fixtures import MockClaimSource, MockStabilitySource
from tests.fixtures.score_fixtures import (
    fixture_claim_bad_source_ref_no_type,
    fixture_claim_empty_id,
    fixture_claim_empty_text,
    fixture_claim_wrong_section,
    fixture_invalid_raw_claim_input,
    fixture_score_claim_container_and_closure,
)


class _AnyPredicateMap(dict):
    """Test-only stand-in for the Phase 5c predicate-resolution
    framework. requirement_id is a fresh uuid4 on every run (see
    evaluator.py's _evaluate_claim_regulatory), so a real predicate
    registry cannot be keyed by it; this always-match mapping exists
    solely to drive this integration test to a conclusive outcome and
    must not be mistaken for a production resolution mechanism."""

    def __init__(self, predicate):
        super().__init__()
        self._predicate = predicate

    def get(self, key, default=None):  # noqa: ARG002
        return self._predicate

    def __bool__(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# 1. Full happy-path pipeline (mechanism verification only)
# ---------------------------------------------------------------------------


class TestHappyPathPipelineMechanism:
    def test_happy_path_pipeline_composes_correctly_not_a_regulatory_conclusion(self, memory_engine):
        """Mechanism check only. The COMPLIANT verdict below comes entirely
        from test-only synthetic fixtures (synthetic_verify_all,
        synthetic_interpreter_requirement, synthetic_predicate_satisfied)
        and proves nothing about any real sponsor claim's regulatory
        compliance."""
        session_id = "sess-5a-happy-path"
        claim = fixture_score_claim_container_and_closure()
        passage = fixture_passage(passage_id="passage-happy-001", question_id="q-happy-001")

        result = run_evaluation(
            memory_engine,
            session_id=session_id,
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
            evidence_source=MockEvidenceSource([passage]),
            question_builder=synthetic_question_builder,
            source_restriction_verifier=synthetic_verify_all,
            passage_interpreter=synthetic_interpreter_requirement,
            applicability_classifier=synthetic_applicability_directly_relevant,
            requirement_evidence_linker=synthetic_linker_none,
            approved_predicates=_AnyPredicateMap(synthetic_predicate_satisfied),
        )

        assert len(result.regulatory) == 1
        claim_result = result.regulatory[0]
        assert claim_result.claim_id == claim.claim_id
        assert claim_result.overall_verdict == Verdict.COMPLIANT
        assert len(claim_result.retrieval_ledger) == 1

        # Persisted independently of the in-memory result.
        findings = get_session_findings(memory_engine, session_id)
        assert len(findings) == 1
        assert findings[0].verdict == Verdict.COMPLIANT
        assert findings[0].claim_id == claim.claim_id
        assert findings[0].event_id == result.event_id
        assert findings[0].session_id == session_id

        events = get_session_events(memory_engine, session_id)
        ledger_events = [e for e in events if e.action == "retrieval_ledger"]
        assert len(ledger_events) == 1
        assert ledger_events[0].parent_event_id == result.event_id

    def test_no_verifier_supplied_still_fails_closed_after_parser_integration(self, memory_engine):
        """The parser-integration change must not weaken the existing,
        approved fail-closed source-verification gate: with no
        source_restriction_verifier supplied (today's real, only
        currently-possible production state), retrieved evidence stays
        unusable even though parser-accepted claims and passages exist."""
        session_id = "sess-5a-fail-closed"
        claim = fixture_score_claim_container_and_closure()
        passage = fixture_passage(passage_id="passage-failclosed-001")

        result = run_evaluation(
            memory_engine,
            session_id=session_id,
            claim_source=MockClaimSource([claim]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
            evidence_source=MockEvidenceSource([passage]),
            question_builder=synthetic_question_builder,
            # source_restriction_verifier intentionally omitted
        )

        assert len(result.regulatory) == 1
        claim_result = result.regulatory[0]
        assert claim_result.overall_verdict == Verdict.INSUFFICIENT_DATA
        assert claim_result.assessments[0].detail["evaluation_path"].startswith(
            "source_restriction_unverifiable"
        )


# ---------------------------------------------------------------------------
# 2. Parser-integration: all five rejection reasons via run_evaluation
# ---------------------------------------------------------------------------


class TestRejectedClaimAuditing:
    def test_mixed_batch_all_five_rejection_reasons_and_one_accepted_claim(self, memory_engine):
        session_id = "sess-5a-mixed-batch"
        accepted = fixture_score_claim_container_and_closure()
        raw_claims = [
            accepted,
            fixture_claim_empty_id(),
            fixture_claim_empty_text(),
            fixture_claim_bad_source_ref_no_type(),
            fixture_claim_wrong_section(),
            fixture_invalid_raw_claim_input(),
        ]

        result = run_evaluation(
            memory_engine,
            session_id=session_id,
            claim_source=MockClaimSource(raw_claims),  # type: ignore[arg-type]
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
            # No evidence/question extension points: this test is about
            # rejection handling, not full regulatory evaluation of the
            # one accepted claim.
        )

        # Only the parser-accepted claim proceeds through the normal
        # evaluation pipeline.
        assert len(result.regulatory) == 1
        assert result.regulatory[0].claim_id == accepted.claim_id

        findings = get_session_findings(memory_engine, session_id)
        events = get_session_events(memory_engine, session_id)

        # 3 structural rejections with a validated id (R2/R3/R4) + 1
        # accepted-claim ("no_question_builder") finding = 4 FindingRecords.
        # Neither R1 (empty_claim_id) nor invalid_input ever produces a
        # FindingRecord -- an empty id is not a validated, usable
        # identifier, so it is audited as a plain event instead, exactly
        # like invalid_input.
        assert len(findings) == 4
        by_claim_id = {f.claim_id: f for f in findings}

        # R1: empty_claim_id -- no FindingRecord at all, not even one
        # with claim_id=None.
        assert not any(
            f.detail.get("evaluation_path") == "claim_rejected_empty_claim_id" for f in findings
        )
        empty_id_events = [e for e in events if e.action == "s6_claim_rejected_empty_claim_id"]
        assert len(empty_id_events) == 1
        assert empty_id_events[0].status == EventStatus.COMPLETED
        assert empty_id_events[0].parent_event_id == result.event_id
        assert "claim_id" not in empty_id_events[0].detail

        # R2/R3/R4: genuine, parser-validated claim_id is carried through.
        assert by_claim_id["c-empty-text"].detail["evaluation_path"] == "claim_rejected_empty_claim_text"
        assert by_claim_id["c-bad-src"].detail["evaluation_path"] == "claim_rejected_invalid_source_ref"
        assert by_claim_id["c-wrong-section"].detail["evaluation_path"] == "claim_rejected_wrong_section"
        for cid in ("c-empty-text", "c-bad-src", "c-wrong-section"):
            assert by_claim_id[cid].verdict == Verdict.INSUFFICIENT_DATA
            assert by_claim_id[cid].requirement_id is None
            assert by_claim_id[cid].event_id == result.event_id
            assert by_claim_id[cid].session_id == session_id

        # invalid_input: no FindingRecord anywhere references the dict's
        # own "claim_id"-shaped value -- it was never a real claim id.
        assert "score-claim-999" not in by_claim_id

        # invalid_input is recorded as a plain AuditEvent instead.
        invalid_input_events = [e for e in events if e.action == "s6_claim_rejected_invalid_input"]
        assert len(invalid_input_events) == 1
        invalid_event = invalid_input_events[0]
        assert invalid_event.status == EventStatus.COMPLETED
        assert invalid_event.parent_event_id == result.event_id
        assert invalid_event.session_id == session_id
        assert invalid_event.agent_name == AgentName.S6_CONTAINER_CLOSURE
        assert invalid_event.detail["reason"] == "invalid_input"
        assert invalid_event.detail["raw_input_type"] == "dict"
        # No fabricated claim id anywhere in the recorded detail.
        assert "claim_id" not in invalid_event.detail

        # Every finding and the invalid-input event trace to this run's
        # own started event -- no cross-session or dangling references.
        action_s6_evaluate = [e for e in events if e.action == "s6_evaluate"]
        assert any(e.status == EventStatus.STARTED for e in action_s6_evaluate)
        assert any(e.status == EventStatus.COMPLETED for e in action_s6_evaluate)

    def test_invalid_input_alone_never_creates_a_finding_record(self, memory_engine):
        session_id = "sess-5a-invalid-input-only"
        result = run_evaluation(
            memory_engine,
            session_id=session_id,
            claim_source=MockClaimSource([fixture_invalid_raw_claim_input()]),  # type: ignore[list-item]
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
        )

        assert result.regulatory == []
        assert get_session_findings(memory_engine, session_id) == []

        events = get_session_events(memory_engine, session_id)
        rejection_events = [e for e in events if e.action == "s6_claim_rejected_invalid_input"]
        assert len(rejection_events) == 1
        assert rejection_events[0].detail["raw_input_repr"]

    def test_empty_claim_id_rejection_never_creates_a_finding_record(self, memory_engine):
        """An empty claim_id is not a validated, usable identifier, so
        this must produce a plain AuditEvent only -- never a
        FindingRecord, not even one with claim_id=None."""
        session_id = "sess-5a-empty-id-only"
        result = run_evaluation(
            memory_engine,
            session_id=session_id,
            claim_source=MockClaimSource([fixture_claim_empty_id()]),
            stability_source=MockStabilitySource([]),
            severity_policy=synthetic_severity_policy,
        )

        assert result.regulatory == []
        assert get_session_findings(memory_engine, session_id) == []

        events = get_session_events(memory_engine, session_id)
        rejection_events = [e for e in events if e.action == "s6_claim_rejected_empty_claim_id"]
        assert len(rejection_events) == 1
        assert rejection_events[0].parent_event_id == result.event_id
        assert rejection_events[0].status == EventStatus.COMPLETED
        assert "claim_id" not in rejection_events[0].detail
