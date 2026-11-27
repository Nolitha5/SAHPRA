"""
Synthetic test fixtures for the S.6 Container Closure Agent evaluator
(Phase 4c).

Rules (same as tests/fixtures/s6_fixtures.py):
* No external service is called. Everything is in-memory.
* No regulatory content is invented. All passage/requirement text is
  clearly labelled as synthetic test data.
* fixture_ prefix on factories; synthetic_/Mock prefix on injected
  extension-point implementations.
"""
from __future__ import annotations

from typing import Any, Sequence

from shared.enums import Severity, Verdict
from shared.models import S6Claim, SourceReference

from container_closure.evaluator import (
    ApplicabilityConfidence,
    InterpretedRequirement,
    PassageInterpretation,
    PassageStatement,
    PredicateAssessment,
    PredicateOutcome,
    RegulatoryQuestion,
    RetrievedPassage,
    SourceVerificationStatus,
)
from container_closure.ports import PortError

from tests.fixtures.s6_fixtures import fixture_source_ref  # reused, not duplicated


# ---------------------------------------------------------------------------
# SourceReference / RegulatoryQuestion / RetrievedPassage factories
# ---------------------------------------------------------------------------


def fixture_m2_source_ref(source_id: str = "m2-passage-001") -> SourceReference:
    return SourceReference(
        source_type="m2_rkb",
        source_id=source_id,
        section="3.2.S.6",
        document="[SYNTHETIC] Test Pharmacopeial Monograph",
        page=1,
    )


def fixture_question(
    question: str = "[SYNTHETIC] Does the closure component satisfy compatibility requirements?",
    assessment_objective: str = "compatibility",
) -> RegulatoryQuestion:
    return RegulatoryQuestion(question=question, assessment_objective=assessment_objective)


def fixture_passage(
    passage_id: str = "passage-001",
    question_id: str = "question-001",
    text: str = (
        "[SYNTHETIC TEST DATA] The container closure system must maintain "
        "integrity throughout the shelf life."
    ),
    ctd_section: str = "3.2.S.6",
) -> RetrievedPassage:
    return RetrievedPassage(
        passage_id=passage_id,
        originating_question_id=question_id,
        ctd_section=ctd_section,
        text=text,
        source_ref=fixture_m2_source_ref(source_id=passage_id),
        source_title="[SYNTHETIC] Test Pharmacopeial Monograph",
        document_id="doc-m2-001",
        pdf_page_number=1,
    )


def fixture_statement(
    passage: RetrievedPassage | None = None,
    interpretation: PassageInterpretation = PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT,
    boundary_confidence: str = "confident",
    span: tuple[int, int] | None = None,
) -> PassageStatement:
    p = passage or fixture_passage()
    text = p.text[span[0] : span[1]] if span is not None else p.text
    return PassageStatement(
        statement_text=text,
        source_passage=p,
        interpretation=interpretation,
        boundary_confidence=boundary_confidence,
        span=span,
    )


def fixture_interpreted_requirement(
    requirement_id: str = "req-001",
    statement: PassageStatement | None = None,
    applicability: ApplicabilityConfidence = ApplicabilityConfidence.DIRECTLY_RELEVANT,
) -> InterpretedRequirement:
    stmt = statement or fixture_statement()
    return InterpretedRequirement(
        requirement_id=requirement_id,
        text=stmt.statement_text,
        citation="[SYNTHETIC] Test Pharmacopeial Monograph -- 3.2.S.6 -- p.1",
        primary_statement=stmt,
        applicability=applicability,
    )


# ---------------------------------------------------------------------------
# Mock RegulatoryEvidenceSource
# ---------------------------------------------------------------------------


class MockEvidenceSource:
    """In-memory RegulatoryEvidenceSource. Returns a fixed list of
    passages regardless of the question asked (sufficient for unit
    tests). Satisfies RegulatoryEvidenceSource structurally."""

    def __init__(
        self,
        passages: list[RetrievedPassage] | None = None,
        *,
        raise_port_error: bool = False,
    ) -> None:
        self._passages: list[RetrievedPassage] = passages if passages is not None else []
        self._raise = raise_port_error

    def search(self, question: RegulatoryQuestion) -> list[RetrievedPassage]:  # noqa: ARG002
        if self._raise:
            raise PortError("MockEvidenceSource: simulated M2 unavailability")
        return list(self._passages)


# ---------------------------------------------------------------------------
# Synthetic QuestionBuilder
# ---------------------------------------------------------------------------


def synthetic_question_builder(claim: S6Claim) -> list[RegulatoryQuestion]:
    return [fixture_question(question=f"[SYNTHETIC] Does the claim '{claim.text}' comply?")]


def synthetic_empty_question_builder(claim: S6Claim) -> list[RegulatoryQuestion]:  # noqa: ARG001
    return []


def synthetic_raising_question_builder(claim: S6Claim) -> list[RegulatoryQuestion]:  # noqa: ARG001
    raise RuntimeError("synthetic question-builder failure")


# ---------------------------------------------------------------------------
# Synthetic SourceRestrictionVerifier
# ---------------------------------------------------------------------------


def synthetic_verify_all(
    passages: Sequence[RetrievedPassage],
) -> dict[str, SourceVerificationStatus]:
    return {p.passage_id: SourceVerificationStatus.VERIFIED for p in passages}


def synthetic_verify_none(
    passages: Sequence[RetrievedPassage],
) -> dict[str, SourceVerificationStatus]:
    return {p.passage_id: SourceVerificationStatus.UNVERIFIABLE for p in passages}


def synthetic_verify_mixed(
    passages: Sequence[RetrievedPassage],
) -> dict[str, SourceVerificationStatus]:
    result: dict[str, SourceVerificationStatus] = {}
    for i, p in enumerate(passages):
        result[p.passage_id] = (
            SourceVerificationStatus.VERIFIED
            if i % 2 == 0
            else SourceVerificationStatus.CONFIRMED_OUTSIDE_SCOPE
        )
    return result


def synthetic_verify_missing_key(
    passages: Sequence[RetrievedPassage],
) -> dict[str, SourceVerificationStatus]:
    result = {p.passage_id: SourceVerificationStatus.VERIFIED for p in passages}
    if result:
        result.pop(next(iter(result)))
    return result


def synthetic_verify_extra_key(
    passages: Sequence[RetrievedPassage],
) -> dict[str, SourceVerificationStatus]:
    result = {p.passage_id: SourceVerificationStatus.VERIFIED for p in passages}
    result["not-a-real-passage-id"] = SourceVerificationStatus.VERIFIED
    return result


def synthetic_verify_invalid_value(passages: Sequence[RetrievedPassage]) -> dict[str, Any]:
    return {p.passage_id: "not-a-status" for p in passages}


def synthetic_raising_verifier(
    passages: Sequence[RetrievedPassage],
) -> dict[str, SourceVerificationStatus]:  # noqa: ARG001
    raise RuntimeError("synthetic verifier failure")


# ---------------------------------------------------------------------------
# Synthetic PassageInterpreter
# ---------------------------------------------------------------------------


def synthetic_interpreter_requirement(
    passage: RetrievedPassage, claim: S6Claim  # noqa: ARG001
) -> list[PassageStatement]:
    return [
        fixture_statement(
            passage=passage, interpretation=PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT
        )
    ]


def synthetic_interpreter_supporting(
    passage: RetrievedPassage, claim: S6Claim  # noqa: ARG001
) -> list[PassageStatement]:
    return [fixture_statement(passage=passage, interpretation=PassageInterpretation.SUPPORTING_INFORMATION)]


def synthetic_interpreter_not_applicable(
    passage: RetrievedPassage, claim: S6Claim  # noqa: ARG001
) -> list[PassageStatement]:
    return [fixture_statement(passage=passage, interpretation=PassageInterpretation.NOT_APPLICABLE)]


def synthetic_interpreter_empty(
    passage: RetrievedPassage, claim: S6Claim  # noqa: ARG001
) -> list[PassageStatement]:
    return []


def synthetic_interpreter_returns_string(passage: RetrievedPassage, claim: S6Claim) -> str:  # noqa: ARG001
    return "this satisfies the Sequence protocol but is not a valid PassageStatement sequence"


def synthetic_interpreter_returns_bytes(passage: RetrievedPassage, claim: S6Claim) -> bytes:  # noqa: ARG001
    return b"also not a valid PassageStatement sequence"


def synthetic_interpreter_returns_bytearray(
    passage: RetrievedPassage, claim: S6Claim  # noqa: ARG001
) -> bytearray:
    return bytearray(b"also not valid")


def synthetic_interpreter_bad_span(
    passage: RetrievedPassage, claim: S6Claim  # noqa: ARG001
) -> list[PassageStatement]:
    return [
        PassageStatement(
            statement_text="this text does not match the span",
            source_passage=passage,
            interpretation=PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT,
            boundary_confidence="confident",
            span=(0, 5),
        )
    ]


def synthetic_interpreter_out_of_bounds_span(
    passage: RetrievedPassage, claim: S6Claim  # noqa: ARG001
) -> list[PassageStatement]:
    huge = len(passage.text) + 1000
    return [
        PassageStatement(
            statement_text=passage.text,
            source_passage=passage,
            interpretation=PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT,
            boundary_confidence="confident",
            span=(0, huge),
        )
    ]


def synthetic_interpreter_mixed_valid_invalid(
    passage: RetrievedPassage, claim: S6Claim  # noqa: ARG001
) -> list[Any]:
    good = fixture_statement(
        passage=passage, interpretation=PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT
    )
    bad = PassageStatement(
        statement_text="not actually present in this passage's text at all",
        source_passage=passage,
        interpretation=PassageInterpretation.SUPPORTING_INFORMATION,
        boundary_confidence="confident",
        span=None,
    )
    return [good, bad]


def synthetic_raising_interpreter(
    passage: RetrievedPassage, claim: S6Claim  # noqa: ARG001
) -> list[PassageStatement]:
    raise RuntimeError("synthetic interpreter failure")


# ---------------------------------------------------------------------------
# Synthetic ApplicabilityClassifier
# ---------------------------------------------------------------------------


def synthetic_applicability_directly_relevant(
    passage: RetrievedPassage, claim: S6Claim  # noqa: ARG001
) -> ApplicabilityConfidence:
    return ApplicabilityConfidence.DIRECTLY_RELEVANT


def synthetic_applicability_uncertain(
    passage: RetrievedPassage, claim: S6Claim  # noqa: ARG001
) -> ApplicabilityConfidence:
    return ApplicabilityConfidence.UNCERTAIN


def synthetic_raising_applicability_classifier(
    passage: RetrievedPassage, claim: S6Claim  # noqa: ARG001
) -> ApplicabilityConfidence:
    raise RuntimeError("synthetic applicability-classifier failure")


def synthetic_applicability_invalid_result(passage: RetrievedPassage, claim: S6Claim) -> str:  # noqa: ARG001
    return "not-a-confidence-value"


# ---------------------------------------------------------------------------
# Synthetic RequirementEvidenceLinker
# ---------------------------------------------------------------------------


def synthetic_linker_none(
    primary: PassageStatement, pool: Sequence[PassageStatement]  # noqa: ARG001
) -> tuple[PassageStatement, ...]:
    return ()


def synthetic_linker_returns_pool(
    primary: PassageStatement, pool: Sequence[PassageStatement]  # noqa: ARG001
) -> list[PassageStatement]:
    return list(pool)


def synthetic_linker_returns_primary(
    primary: PassageStatement, pool: Sequence[PassageStatement]  # noqa: ARG001
) -> list[PassageStatement]:
    return [primary]


def synthetic_linker_returns_duplicates(
    primary: PassageStatement, pool: Sequence[PassageStatement]  # noqa: ARG001
) -> list[PassageStatement]:
    if not pool:
        return []
    return [pool[0], pool[0]]


def synthetic_linker_returns_foreign(
    primary: PassageStatement, pool: Sequence[PassageStatement]  # noqa: ARG001
) -> list[PassageStatement]:
    foreign_passage = fixture_passage(passage_id="not-in-pool")
    return [
        fixture_statement(passage=foreign_passage, interpretation=PassageInterpretation.SUPPORTING_INFORMATION)
    ]


def synthetic_raising_linker(
    primary: PassageStatement, pool: Sequence[PassageStatement]  # noqa: ARG001
) -> list[PassageStatement]:
    raise RuntimeError("synthetic linker failure")


# ---------------------------------------------------------------------------
# Synthetic ApprovedPredicate implementations
# ---------------------------------------------------------------------------


def synthetic_predicate_satisfied(
    claim: S6Claim, requirement: InterpretedRequirement  # noqa: ARG001
) -> PredicateAssessment:
    return PredicateAssessment(
        outcome=PredicateOutcome.SATISFIED,
        rationale="[SYNTHETIC] The sponsor's own evidence directly satisfies this requirement.",
        source_refs=(fixture_source_ref(),),
    )


def synthetic_predicate_breached(
    claim: S6Claim, requirement: InterpretedRequirement  # noqa: ARG001
) -> PredicateAssessment:
    return PredicateAssessment(
        outcome=PredicateOutcome.BREACHED,
        rationale="[SYNTHETIC] The sponsor's own evidence contradicts this requirement.",
        source_refs=(fixture_source_ref(),),
    )


def synthetic_predicate_indeterminate(
    claim: S6Claim, requirement: InterpretedRequirement  # noqa: ARG001
) -> PredicateAssessment:
    return PredicateAssessment(
        outcome=PredicateOutcome.INDETERMINATE,
        rationale="[SYNTHETIC] Cannot determine satisfaction or breach from available evidence.",
    )


def synthetic_predicate_satisfied_no_evidence(
    claim: S6Claim, requirement: InterpretedRequirement  # noqa: ARG001
) -> PredicateAssessment:
    return PredicateAssessment(
        outcome=PredicateOutcome.SATISFIED,
        rationale="[SYNTHETIC] Satisfied but no supporting source references supplied.",
    )


def synthetic_predicate_missing_rationale(
    claim: S6Claim, requirement: InterpretedRequirement  # noqa: ARG001
) -> PredicateAssessment:
    return PredicateAssessment(
        outcome=PredicateOutcome.SATISFIED,
        rationale="   ",
        source_refs=(fixture_source_ref(),),
    )


def synthetic_predicate_invalid_result(
    claim: S6Claim, requirement: InterpretedRequirement  # noqa: ARG001
) -> str:
    return "not-a-predicate-assessment"


def synthetic_raising_predicate(
    claim: S6Claim, requirement: InterpretedRequirement  # noqa: ARG001
) -> PredicateAssessment:
    raise RuntimeError("synthetic predicate failure")


# ---------------------------------------------------------------------------
# Synthetic SeverityPolicy implementations
# ---------------------------------------------------------------------------

_SEVERITY_BY_VERDICT = {
    Verdict.COMPLIANT: Severity.INFO,
    Verdict.NON_COMPLIANT: Severity.CRITICAL,
    Verdict.NEEDS_REVIEW: Severity.MAJOR,
    Verdict.INSUFFICIENT_DATA: Severity.MINOR,
}


def synthetic_severity_policy(verdict: Verdict, detail: dict[str, Any]) -> Severity:  # noqa: ARG001
    return _SEVERITY_BY_VERDICT[verdict]


def synthetic_raising_severity_policy(verdict: Verdict, detail: dict[str, Any]) -> Severity:  # noqa: ARG001
    raise RuntimeError("synthetic severity-policy failure")


def synthetic_severity_policy_wrong_type(verdict: Verdict, detail: dict[str, Any]) -> str:  # noqa: ARG001
    return "not-a-severity"


class _InconsistentSeverityPolicy:
    """Deliberately returns a different Severity for the same
    (verdict, evaluation_path) pair across calls within one run."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()

    def __call__(self, verdict: Verdict, detail: dict[str, Any]) -> Severity:
        key = (verdict.value, detail.get("evaluation_path", ""))
        if key in self._seen:
            return Severity.CRITICAL
        self._seen.add(key)
        return Severity.INFO


def make_inconsistent_severity_policy() -> _InconsistentSeverityPolicy:
    return _InconsistentSeverityPolicy()
