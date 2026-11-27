"""
S.6 Container Closure Agent -- Phase 4c regulatory evaluator.

Scope and architectural position
----------------------------------
This module implements the approved Phase 4c design (eight design rounds,
2026-11-23): it evaluates sponsor packaging claims (S6Claim, from Phase 1)
against regulatory evidence retrieved from M2, and reports the result
through the existing Tier 0 audit layer (shared/audit.py, unmodified).

It supersedes, for its own purposes only, the Phase 4a
`container_closure.ports.RequirementSource` protocol and
`shared.models.RKBRequirement` model. Those assumed a single free-text
topic query returning ready-made, validated, atomic requirements. M2's
own confirmed integration contract is different: it takes a
natural-language question plus a CTD section and optional filters
(POST /api/search / RetrievalService.retrieve), and returns CANDIDATE
RETRIEVED PASSAGES -- M2 has explicitly stated its RKB returns candidate
evidence passages and findings, not a validated list of atomic
regulatory requirements. Neither `ports.py` nor `models.py` is modified
by this module; `RequirementSource`/`RKBRequirement` are simply not used
here. Whether to retire them project-wide is a decision for whoever owns
those Phase 1-4a files.

Three distinct concepts, never treated as interchangeable:
  A. RetrievedPassage        -- a retrieved regulatory evidence passage.
  B. InterpretedRequirement  -- S6's interpretation of a potentially
                                 applicable requirement, built from
                                 exactly one PassageStatement that was
                                 itself classified
                                 POTENTIALLY_APPLICABLE_REQUIREMENT.
  C. RequirementAssessment / FindingRecord
                              -- S6's own finding assessing the sponsor's
                                 claim against (B), never itself evidence.

CRITICAL, FIRM project requirement -- pharmacist/client source
restriction: S6 may use retrieved evidence only from the "Pharmacopeial
Monographs" and "Others" categories (see PHARMACIST_APPROVED_SOURCE_
CATEGORIES below). The exact M2 request/response field that carries
category information has NOT been confirmed. This module therefore
FAILS CLOSED by construction: with no SourceRestrictionVerifier
supplied -- today's actual state -- every retrieved passage is treated
as UNVERIFIABLE and NONE of it is interpreted or assessed; every
affected claim instead receives an INSUFFICIENT_DATA finding naming the
reason. No M2 filter or response field name is invented anywhere in this
module. The evaluator does not, and currently cannot, perform a
regulatory assessment using retrieved evidence until a real verifier,
confirmed against M2's actual category representation, is supplied.

Every semantic judgement (which question to ask, whether a retrieved
passage belongs to an approved category, what a passage statement means,
whether it applies to a given claim, which statements corroborate a
requirement, whether a claim satisfies or breaches a requirement, what
severity a finding deserves) is an injected, caller-supplied extension
point. None of them is implemented with keyword matching, an LLM, or any
other inference inside this module -- every extension point defaults to
the safest, most conservative behaviour when not supplied, and no
exception or invalid result from any of them can ever silently produce a
COMPLIANT or NON_COMPLIANT verdict.

Cross-section boundary: S7 stability information is linked against S6
claims via the unmodified Phase 4b `stability_linker.link_stability_
conditions`, and its LinkResult is carried on EvaluationRunResult
verbatim. No LinkClassification is ever converted into a Verdict here --
S7 information can never, by itself, produce a regulatory finding. This
module never writes a FindingType.CONTRADICTION finding; that remains
reserved for the separate, not-yet-authorized Cross-Section Consistency
Agent.

Audit integration: every FindingRecord and the one retrieval-ledger
AuditEvent per claim are written inside a single `execution_scope`
per run, using only the existing, unmodified `write_event`/`write_finding`
functions. No new audit action enum, event status, or schema change is
introduced -- `AuditEvent.action` is already a free string and
`AuditEvent.detail`/`FindingRecord.detail` are already free-form JSON
fields.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence, runtime_checkable

from sqlalchemy.engine import Engine

from container_closure.parser import ParseRejection, parse_claims
from container_closure.ports import ClaimSource, PortError, StabilitySource
from container_closure.stability_linker import LinkResult, link_stability_conditions
from shared.audit import execution_scope, write_event, write_finding
from shared.enums import AgentName, EventStatus, FindingType, Severity, Verdict
from shared.exceptions import AuditWriteError, S6BaseError
from shared.models import AuditEvent, FindingRecord, S6Claim, SourceReference


# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

#: Exact pharmacist/client-approved source category labels. These are
#: project policy labels ONLY -- never M2 field names or filter values.
#: M2 has not confirmed which field or metadata structure carries
#: source-category information on either the request or response side;
#: until it does, no SourceRestrictionVerifier can be implemented against
#: a real M2 contract, and the fail-closed default in
#: `_verify_source_restriction` applies.
PHARMACIST_APPROVED_SOURCE_CATEGORIES: frozenset[str] = frozenset(
    {"Pharmacopeial Monographs", "Others"}
)


# ---------------------------------------------------------------------------
# Local exceptions (deliberately not added to shared/exceptions.py)
# ---------------------------------------------------------------------------


class SeverityPolicyError(S6BaseError):
    """Raised when a caller-supplied severity_policy misbehaves: it
    raises, returns a value that is not a Severity member, or returns
    inconsistent results for the same (verdict, evaluation_path) pair
    within one run. Never caught inside run_evaluation() -- it is a
    run-level configuration defect that aborts the run (via
    execution_scope's own, unmodified failed-event handling), never a
    reason to substitute an arbitrary severity."""


class EvaluatorRunAborted(S6BaseError):
    """Wraps a run-level audit-write failure (AuditWriteError from
    write_event/write_finding) with claim-level context before letting
    it propagate into execution_scope's existing failed-event handling.
    Always raised with `from exc` so the original cause is preserved."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ApplicabilityConfidence(str, Enum):
    """S6's own judgement of whether a retrieved passage is relevant to
    the SPECIFIC sponsor claim being assessed. Never derived from, and
    never substituted for, M2's own RegulatoryQuestion.applicability_
    statuses request filter -- the two are independent concepts
    (approved design, round 5, point 3)."""

    DIRECTLY_RELEVANT = "directly_relevant"
    POSSIBLY_RELEVANT = "possibly_relevant"
    UNCERTAIN = "uncertain"


class PassageInterpretation(str, Enum):
    """What kind of content one identified statement within a retrieved
    passage appears to be. Only POTENTIALLY_APPLICABLE_REQUIREMENT may
    ever be promoted into an InterpretedRequirement."""

    POTENTIALLY_APPLICABLE_REQUIREMENT = "potentially_applicable_requirement"
    SUPPORTING_INFORMATION = "supporting_information"
    NOT_APPLICABLE = "not_applicable"
    UNCERTAIN_INTERPRETATION = "uncertain_interpretation"


class SourceVerificationStatus(str, Enum):
    """Per-passage disposition from a SourceRestrictionVerifier. Only
    VERIFIED passages may ever proceed to interpretation."""

    VERIFIED = "verified"
    CONFIRMED_OUTSIDE_SCOPE = "confirmed_outside_scope"
    UNVERIFIABLE = "unverifiable"


class PredicateOutcome(str, Enum):
    """The substantive judgement an ApprovedPredicate reaches about one
    (claim, InterpretedRequirement) pair."""

    SATISFIED = "satisfied"
    BREACHED = "breached"
    INDETERMINATE = "indeterminate"


# ---------------------------------------------------------------------------
# Data structures -- retrieval (concept A)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegulatoryQuestion:
    """A natural-language regulatory assessment question to submit to
    M2, shaped around M2's confirmed /api/search contract (query,
    filters.ctd_sections, filters.include_parent_sections,
    filters.applicability_statuses, final_k).

    `assessment_objective` is a question-PREPARATION label only -- one of
    S6's five named responsibility areas (container description, closure
    components, compatibility, protection and integrity, storage
    statements). It carries no presumption that a requirement exists for
    it, and it is never used to infer that a retrieved passage is
    applicable.

    `applicability_statuses` belongs entirely to this retrieval request
    contract (M2's own notion of source status filtering) and must never
    be confused with S6's own ApplicabilityConfidence (see that class's
    docstring).
    """

    question: str
    ctd_sections: tuple[str, ...] = ("3.2.S.6",)
    include_parent_sections: bool = False
    applicability_statuses: tuple[str, ...] | None = None
    final_k: int | None = None
    assessment_objective: str = ""
    question_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass(frozen=True)
class RetrievedPassage:
    """One retrieved regulatory evidence passage from M2.

    Field names represent S6's own model of the provenance concepts
    M2's integration clarification confirmed exist (source title,
    issuing organisation, document identifier, version/date metadata,
    CTD section, PDF page number, printed page label, chunk IDs,
    retrieval scores) -- they are NOT assumed to be M2's literal
    response JSON keys, which remain unconfirmed. Mapping the real M2
    response into this shape is adapter work, outside this module's
    scope. `retrieval_metadata` preserves anything else M2 returns,
    confirmed or not, rather than discarding it.

    This is NOT a regulatory requirement -- see PassageInterpretation.
    """

    passage_id: str
    originating_question_id: str
    ctd_section: str
    text: str
    source_ref: SourceReference
    chunk_id: str | None = None
    source_title: str | None = None
    issuing_organisation: str | None = None
    document_id: str | None = None
    document_version: str | None = None
    document_date: str | None = None
    pdf_page_number: int | None = None
    printed_page_label: str | None = None
    retrieval_score: float | None = None
    retrieval_metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Data structures -- interpretation (concept B)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PassageStatement:
    """One identified statement within a retrieved passage.

    `statement_text` MUST be a verbatim substring of
    `source_passage.text` (or exactly equal to it) -- S6 never
    paraphrases or invents requirement wording; this is validated by
    `_validate_statement`. `span`, when given, is a (start, end)
    character offset into `source_passage.text`, also validated.
    """

    statement_text: str
    source_passage: RetrievedPassage
    interpretation: PassageInterpretation
    boundary_confidence: Literal["confident", "uncertain"]
    span: tuple[int, int] | None = None


@dataclass(frozen=True)
class PassageStatementSummary:
    """Ledger-facing summary of one PassageStatement, carrying enough
    detail (exact text, span, outcome) for an auditor to reconstruct
    what happened to it without re-running any code."""

    statement_text: str
    span: tuple[int, int] | None
    interpretation: PassageInterpretation
    boundary_confidence: Literal["confident", "uncertain"]
    became_requirement_id: str | None = None
    used_as_supporting_for: tuple[str, ...] = ()


@dataclass(frozen=True)
class InterpretedRequirement:
    """S6's interpretation of a potentially applicable requirement,
    built from exactly one PassageStatement classified
    POTENTIALLY_APPLICABLE_REQUIREMENT ("primary_statement").

    `text` is always `primary_statement.statement_text`, verbatim.
    `supporting_statements` may corroborate the SAME requirement from
    other statements (possibly other passages/questions) but can never
    supply or alter the requirement's own wording, and being selected as
    supporting evidence here never itself promotes a statement into
    becoming a second, separate requirement -- requirement creation is
    driven solely by PassageInterpretation classification.
    """

    requirement_id: str
    text: str
    citation: str
    primary_statement: PassageStatement
    applicability: ApplicabilityConfidence
    supporting_statements: tuple[PassageStatement, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Data structures -- predicate / assessment (concept C)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PredicateAssessment:
    """The structured result an ApprovedPredicate must return. A bare
    bool/None cannot carry a rationale or evidence, so this replaces
    that shape entirely."""

    outcome: PredicateOutcome
    rationale: str
    citation: str | None = None
    source_refs: tuple[SourceReference, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RequirementAssessment:
    claim_id: str
    requirement_id: str | None
    verdict: Verdict
    severity: Severity
    rationale: str
    citation: str | None
    source_refs: tuple[SourceReference, ...]
    detail: dict[str, Any]


@dataclass(frozen=True)
class RetrievalLedgerEntry:
    """One entry per passage M2 ever returned for a claim, regardless of
    disposition -- the authoritative record of what was retrieved and
    why it was or was not used, independent of whether it produced a
    FindingRecord."""

    passage_id: str
    originating_question_id: str
    source_ref: SourceReference
    verification_status: SourceVerificationStatus
    statements: tuple[PassageStatementSummary, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClaimRegulatoryResult:
    claim_id: str
    assessments: tuple[RequirementAssessment, ...]
    overall_verdict: Verdict
    retrieval_ledger: tuple[RetrievalLedgerEntry, ...] = ()


@dataclass
class EvaluationRunResult:
    session_id: str
    event_id: str
    regulatory: list[ClaimRegulatoryResult]
    cross_section: LinkResult | None
    cross_section_status: str
    finding_ids: list[str]


# ---------------------------------------------------------------------------
# Extension points (all injected; every one defaults to the safest,
# most conservative behaviour when not supplied -- none is ever guessed)
# ---------------------------------------------------------------------------


@runtime_checkable
class RegulatoryEvidenceSource(Protocol):
    """Protocol for M2's confirmed retrieval contract (/api/search or
    RetrievalService.retrieve). Supersedes container_closure.ports.
    RequirementSource for Phase 4c's purposes only -- see module
    docstring. Not added to ports.py (Phase 1-4a, outside this phase's
    authorized scope)."""

    def search(self, question: RegulatoryQuestion) -> Sequence[RetrievedPassage]:
        """Raises PortError on failure; an empty sequence is a valid
        'nothing retrieved' result."""
        ...


QuestionBuilder = Callable[[S6Claim], Sequence[RegulatoryQuestion]]
SourceRestrictionVerifier = Callable[
    [Sequence[RetrievedPassage]], Mapping[str, SourceVerificationStatus]
]
PassageInterpreterFn = Callable[[RetrievedPassage, S6Claim], Sequence[PassageStatement]]
ApplicabilityClassifierFn = Callable[[RetrievedPassage, S6Claim], ApplicabilityConfidence]
RequirementEvidenceLinkerFn = Callable[
    [PassageStatement, Sequence[PassageStatement]], Sequence[PassageStatement]
]
ApprovedPredicate = Callable[[S6Claim, InterpretedRequirement], PredicateAssessment]
SeverityPolicy = Callable[[Verdict, dict[str, Any]], Severity]


# ---------------------------------------------------------------------------
# Validation helpers -- PassageInterpreter
# ---------------------------------------------------------------------------


def _is_rejected_scalar_sequence(value: Any) -> bool:
    """True for the specific invalid-but-technically-Sequence-protocol
    values that must be rejected explicitly: str, bytes and bytearray
    all satisfy Python's Sequence protocol but are never a valid
    sequence of PassageStatement objects."""
    return isinstance(value, (str, bytes, bytearray))


def _validate_statement(stmt: Any, passage: RetrievedPassage) -> str | None:
    """Return None if `stmt` is a valid PassageStatement whose
    statement_text/span are genuinely represented by `passage`;
    otherwise return a short machine-readable reason string."""
    if not isinstance(stmt, PassageStatement):
        return "not_a_passage_statement"
    if stmt.source_passage.passage_id != passage.passage_id:
        return "statement_references_different_passage"
    if not isinstance(stmt.interpretation, PassageInterpretation):
        return "invalid_interpretation_value"
    if stmt.boundary_confidence not in ("confident", "uncertain"):
        return "invalid_boundary_confidence"
    if stmt.span is not None:
        if (
            not isinstance(stmt.span, tuple)
            or len(stmt.span) != 2
            or not all(isinstance(v, int) for v in stmt.span)
        ):
            return "invalid_span_type"
        start, end = stmt.span
        if not (0 <= start <= end <= len(passage.text)):
            return "span_out_of_bounds"
        if passage.text[start:end] != stmt.statement_text:
            return "span_text_mismatch"
    else:
        if stmt.statement_text not in passage.text:
            return "statement_text_not_in_passage"
    return None


def _uncertain_fallback_statement(passage: RetrievedPassage) -> PassageStatement:
    return PassageStatement(
        statement_text=passage.text,
        source_passage=passage,
        interpretation=PassageInterpretation.UNCERTAIN_INTERPRETATION,
        boundary_confidence="uncertain",
        span=None,
    )


def _interpret_passage(
    passage: RetrievedPassage,
    claim: S6Claim,
    interpreter: PassageInterpreterFn | None,
) -> tuple[list[PassageStatement], dict[str, Any]]:
    """Run `interpreter` for one passage with full validation. Returns
    (valid_statements, ledger_detail). valid_statements is never empty
    -- on any failure, exactly the single uncertain-fallback statement
    is returned, and the passage is never silently dropped from the
    record."""
    if interpreter is None:
        return [_uncertain_fallback_statement(passage)], {
            "evaluation_path": "no_passage_interpreter"
        }

    try:
        raw = interpreter(passage, claim)
    except Exception as exc:  # noqa: BLE001 -- must not propagate (per-passage isolation)
        return [_uncertain_fallback_statement(passage)], {
            "evaluation_path": "passage_interpreter_error",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }

    if _is_rejected_scalar_sequence(raw):
        return [_uncertain_fallback_statement(passage)], {
            "evaluation_path": "passage_interpreter_invalid_result",
            "invalid_reason": f"result was {type(raw).__name__}, not a sequence of PassageStatement",
        }

    try:
        candidates = list(raw)
    except TypeError:
        return [_uncertain_fallback_statement(passage)], {
            "evaluation_path": "passage_interpreter_invalid_result",
            "invalid_reason": "result is not iterable",
        }

    if len(candidates) == 0:
        return [_uncertain_fallback_statement(passage)], {
            "evaluation_path": "passage_interpreter_empty_result"
        }

    valid: list[PassageStatement] = []
    rejected: list[dict[str, Any]] = []
    for stmt in candidates:
        reason = _validate_statement(stmt, passage)
        if reason is None:
            valid.append(stmt)
        else:
            rejected.append({"reason": reason})

    if not valid:
        detail: dict[str, Any] = {"evaluation_path": "passage_interpreter_invalid_result"}
        if rejected:
            detail["rejected_statements"] = rejected
        return [_uncertain_fallback_statement(passage)], detail

    detail = {"evaluation_path": "passage_interpreted"}
    if rejected:
        detail["rejected_statements"] = rejected
    return valid, detail


# ---------------------------------------------------------------------------
# Validation helpers -- applicability_classifier
# ---------------------------------------------------------------------------


def _classify_applicability(
    passage: RetrievedPassage,
    claim: S6Claim,
    classifier: ApplicabilityClassifierFn | None,
) -> tuple[ApplicabilityConfidence, dict[str, Any]]:
    if classifier is None:
        return ApplicabilityConfidence.UNCERTAIN, {"evaluation_path": "no_applicability_classifier"}
    try:
        result = classifier(passage, claim)
    except Exception as exc:  # noqa: BLE001
        return ApplicabilityConfidence.UNCERTAIN, {
            "evaluation_path": "applicability_classifier_error",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }
    if not isinstance(result, ApplicabilityConfidence):
        return ApplicabilityConfidence.UNCERTAIN, {
            "evaluation_path": "applicability_classifier_invalid_result"
        }
    return result, {}


# ---------------------------------------------------------------------------
# Validation helpers -- RequirementEvidenceLinker
# ---------------------------------------------------------------------------


def _statement_key(stmt: PassageStatement) -> tuple[str, Any, str]:
    return (stmt.source_passage.passage_id, stmt.span, stmt.statement_text)


def _link_supporting_statements(
    primary: PassageStatement,
    pool: Sequence[PassageStatement],
    linker: RequirementEvidenceLinkerFn | None,
) -> tuple[tuple[PassageStatement, ...], dict[str, Any]]:
    """Validates every candidate the linker proposes: the primary
    statement cannot appear among its own supporting statements, every
    candidate must belong to `pool` (this claim's retrieved evidence),
    and duplicates are dropped. Invalid candidates are dropped
    individually rather than invalidating the whole call."""
    if linker is None:
        return (), {}

    try:
        raw = linker(primary, pool)
    except Exception as exc:  # noqa: BLE001
        return (), {
            "linker_evaluation_path": "linker_error",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }

    if _is_rejected_scalar_sequence(raw):
        return (), {"linker_evaluation_path": "linker_invalid_result"}
    try:
        candidates = list(raw)
    except TypeError:
        return (), {"linker_evaluation_path": "linker_invalid_result"}

    pool_keys = {_statement_key(s) for s in pool}
    primary_key = _statement_key(primary)
    accepted: list[PassageStatement] = []
    seen: set[tuple[str, Any, str]] = set()
    dropped: list[dict[str, Any]] = []
    for cand in candidates:
        if not isinstance(cand, PassageStatement):
            dropped.append({"reason": "not_a_passage_statement"})
            continue
        key = _statement_key(cand)
        if key == primary_key:
            dropped.append({"reason": "linker_excluded_primary_as_supporting"})
            continue
        if key not in pool_keys:
            dropped.append({"reason": "linker_candidate_not_in_pool"})
            continue
        if key in seen:
            dropped.append({"reason": "linker_duplicate_candidate"})
            continue
        seen.add(key)
        accepted.append(cand)

    detail: dict[str, Any] = {}
    if dropped:
        detail["linker_dropped"] = dropped
    return tuple(accepted), detail


# ---------------------------------------------------------------------------
# Validation helpers -- SourceRestrictionVerifier (fail-closed gate)
# ---------------------------------------------------------------------------


def _verify_source_restriction(
    passages: Sequence[RetrievedPassage],
    verifier: SourceRestrictionVerifier | None,
) -> tuple[dict[str, SourceVerificationStatus], dict[str, Any]]:
    """Returns (passage_id -> status, claim-level detail). FAILS CLOSED:
    on any problem (no verifier, an exception, or an invalid result),
    every passage_id maps to UNVERIFIABLE and none may proceed."""
    ids = [p.passage_id for p in passages]

    if len(ids) != len(set(ids)):
        return {pid: SourceVerificationStatus.UNVERIFIABLE for pid in ids}, {
            "evaluation_path": "source_restriction_duplicate_input_ids"
        }

    if verifier is None:
        return {pid: SourceVerificationStatus.UNVERIFIABLE for pid in ids}, {
            "evaluation_path": "source_restriction_unverifiable_no_verifier",
            "approved_categories_policy": sorted(PHARMACIST_APPROVED_SOURCE_CATEGORIES),
            "passages_considered": len(ids),
            "passages_verified": 0,
        }

    try:
        raw = verifier(passages)
    except Exception as exc:  # noqa: BLE001
        return {pid: SourceVerificationStatus.UNVERIFIABLE for pid in ids}, {
            "evaluation_path": "source_restriction_verifier_error",
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "passages_considered": len(ids),
            "passages_verified": 0,
        }

    try:
        result = dict(raw)
    except (TypeError, ValueError):
        return {pid: SourceVerificationStatus.UNVERIFIABLE for pid in ids}, {
            "evaluation_path": "source_restriction_verifier_invalid_result",
            "invalid_reason": "result is not a mapping",
            "passages_considered": len(ids),
            "passages_verified": 0,
        }

    id_set = set(ids)
    if set(result.keys()) != id_set:
        return {pid: SourceVerificationStatus.UNVERIFIABLE for pid in ids}, {
            "evaluation_path": "source_restriction_verifier_invalid_result",
            "invalid_reason": "result keys do not match exactly the input passage ids",
            "passages_considered": len(ids),
            "passages_verified": 0,
        }
    if not all(isinstance(v, SourceVerificationStatus) for v in result.values()):
        return {pid: SourceVerificationStatus.UNVERIFIABLE for pid in ids}, {
            "evaluation_path": "source_restriction_verifier_invalid_result",
            "invalid_reason": "result contains a non-SourceVerificationStatus value",
            "passages_considered": len(ids),
            "passages_verified": 0,
        }

    verified_count = sum(1 for v in result.values() if v == SourceVerificationStatus.VERIFIED)
    if verified_count == 0:
        path = "source_restriction_none_verified"
    elif verified_count < len(ids):
        path = "source_restriction_partially_verified"
    else:
        path = "source_restriction_fully_verified"
    detail = {
        "evaluation_path": path,
        "approved_categories_policy": sorted(PHARMACIST_APPROVED_SOURCE_CATEGORIES),
        "passages_considered": len(ids),
        "passages_verified": verified_count,
    }
    return result, detail


# ---------------------------------------------------------------------------
# Predicate evaluation
# ---------------------------------------------------------------------------


def _citation_from_passage(p: RetrievedPassage) -> str:
    """Derived purely from the passage's own retained fields -- never
    invented text."""
    parts = [p.source_title or p.document_id or p.passage_id, p.ctd_section]
    if p.pdf_page_number is not None:
        parts.append(f"p.{p.pdf_page_number}")
    return " -- ".join(str(x) for x in parts if x)


def _evaluate_predicate(
    claim: S6Claim,
    requirement: InterpretedRequirement,
    predicates: Mapping[str, ApprovedPredicate],
) -> tuple[Verdict, str, dict[str, Any], str | None, tuple[SourceReference, ...]]:
    """Returns (verdict, rationale, detail, citation, source_refs). No
    exception or invalid predicate result can ever produce COMPLIANT or
    NON_COMPLIANT here."""
    base_refs = (claim.source_ref, requirement.primary_statement.source_passage.source_ref)

    predicate = predicates.get(requirement.requirement_id)
    if predicate is None:
        return (
            Verdict.NEEDS_REVIEW,
            f"No approved predicate is registered for requirement '{requirement.requirement_id}'.",
            {"evaluation_path": "no_predicate"},
            requirement.citation,
            base_refs,
        )

    try:
        result = predicate(claim, requirement)
    except Exception as exc:  # noqa: BLE001
        return (
            Verdict.NEEDS_REVIEW,
            f"Approved predicate for requirement '{requirement.requirement_id}' raised an exception.",
            {
                "evaluation_path": "predicate_error",
                "predicate_error_type": type(exc).__name__,
                "predicate_error_message": str(exc),
            },
            requirement.citation,
            base_refs,
        )

    if not isinstance(result, PredicateAssessment):
        return (
            Verdict.NEEDS_REVIEW,
            f"Approved predicate for requirement '{requirement.requirement_id}' returned an invalid result.",
            {"evaluation_path": "predicate_invalid_result", "invalid_reason": "not_a_predicate_assessment"},
            requirement.citation,
            base_refs,
        )
    if not isinstance(result.outcome, PredicateOutcome):
        return (
            Verdict.NEEDS_REVIEW,
            f"Approved predicate for requirement '{requirement.requirement_id}' returned an invalid outcome.",
            {"evaluation_path": "predicate_invalid_result", "invalid_reason": "invalid_outcome"},
            requirement.citation,
            base_refs,
        )
    if not isinstance(result.rationale, str) or not result.rationale.strip():
        return (
            Verdict.NEEDS_REVIEW,
            f"Approved predicate for requirement '{requirement.requirement_id}' returned no rationale.",
            {"evaluation_path": "predicate_invalid_result", "invalid_reason": "missing_rationale"},
            requirement.citation,
            base_refs,
        )

    citation = result.citation or requirement.citation
    merged_refs = base_refs + tuple(result.source_refs)

    if result.outcome is PredicateOutcome.INDETERMINATE:
        return (
            Verdict.NEEDS_REVIEW,
            result.rationale,
            {"evaluation_path": "predicate_indeterminate", **result.detail},
            citation,
            merged_refs,
        )

    # Conclusive outcomes (SATISFIED / BREACHED) require their own evidence
    # -- the requirement's own citation is never treated as proof by itself.
    if not result.source_refs or not all(isinstance(r, SourceReference) for r in result.source_refs):
        return (
            Verdict.NEEDS_REVIEW,
            (
                f"Approved predicate for requirement '{requirement.requirement_id}' reached a "
                f"conclusive outcome without supporting source references."
            ),
            {"evaluation_path": "predicate_missing_evidence"},
            citation,
            merged_refs,
        )

    # Safeguard: an uncertain statement boundary downgrades any conclusive outcome.
    if requirement.primary_statement.boundary_confidence == "uncertain":
        return (
            Verdict.NEEDS_REVIEW,
            (
                f"Predicate outcome for requirement '{requirement.requirement_id}' is not trusted "
                f"because its originating statement's boundary is uncertain."
            ),
            {
                "evaluation_path": "requirement_boundary_uncertain",
                "predicate_outcome": result.outcome.value,
            },
            citation,
            merged_refs,
        )

    # Safeguard: uncertain claim-applicability downgrades any conclusive outcome.
    if requirement.applicability == ApplicabilityConfidence.UNCERTAIN:
        path = (
            "predicate_satisfied_without_evidence"
            if result.outcome is PredicateOutcome.SATISFIED
            else "predicate_breached_without_evidence"
        )
        return (
            Verdict.NEEDS_REVIEW,
            (
                f"Predicate outcome for requirement '{requirement.requirement_id}' is not trusted "
                f"because the requirement's applicability to this claim is uncertain."
            ),
            {"evaluation_path": path},
            citation,
            merged_refs,
        )

    if result.outcome is PredicateOutcome.SATISFIED:
        return (
            Verdict.COMPLIANT,
            result.rationale,
            {"evaluation_path": "predicate_satisfied", **result.detail},
            citation,
            merged_refs,
        )
    return (
        Verdict.NON_COMPLIANT,
        result.rationale,
        {"evaluation_path": "predicate_breached", **result.detail},
        citation,
        merged_refs,
    )


# ---------------------------------------------------------------------------
# Severity policy -- required, no default, no silent substitution
# ---------------------------------------------------------------------------


def _assign_severity(
    verdict: Verdict,
    detail: dict[str, Any],
    policy: SeverityPolicy,
    *,
    seen: dict[tuple[Verdict, str], Severity],
) -> Severity:
    """Calls the caller-supplied severity_policy exactly once. Any
    exception, a non-Severity return value, or a same-situation
    inconsistency within this run is wrapped and re-raised as
    SeverityPolicyError -- never swallowed, never silently substituted."""
    path = detail.get("evaluation_path", "")
    key = (verdict, path)
    try:
        result = policy(verdict, detail)
    except Exception as exc:  # noqa: BLE001 -- caught only to wrap with context, then re-raised
        raise SeverityPolicyError(
            f"severity_policy raised for verdict={verdict.value} evaluation_path={path!r}: {exc}"
        ) from exc
    if not isinstance(result, Severity):
        raise SeverityPolicyError(
            f"severity_policy returned {result!r} (not a Severity member) for "
            f"verdict={verdict.value} evaluation_path={path!r}"
        )
    previous = seen.get(key)
    if previous is not None and previous != result:
        raise SeverityPolicyError(
            f"severity_policy returned inconsistent results for the same "
            f"(verdict={verdict.value}, evaluation_path={path!r}): "
            f"first {previous.value}, now {result.value}"
        )
    seen[key] = result
    return result


# ---------------------------------------------------------------------------
# Claim-level roll-up
# ---------------------------------------------------------------------------


def _overall_verdict(assessments: Sequence[RequirementAssessment]) -> Verdict:
    """NON_COMPLIANT > NEEDS_REVIEW > INSUFFICIENT_DATA > COMPLIANT.
    `assessments` is guaranteed never empty by every caller in this
    module, so COMPLIANT is reachable only when every entry is
    COMPLIANT."""
    verdicts = {a.verdict for a in assessments}
    if Verdict.NON_COMPLIANT in verdicts:
        return Verdict.NON_COMPLIANT
    if Verdict.NEEDS_REVIEW in verdicts:
        return Verdict.NEEDS_REVIEW
    if Verdict.INSUFFICIENT_DATA in verdicts:
        return Verdict.INSUFFICIENT_DATA
    return Verdict.COMPLIANT


# ---------------------------------------------------------------------------
# JSON-safe serialization for the retrieval ledger
# ---------------------------------------------------------------------------


def _source_ref_to_json(ref: SourceReference) -> dict[str, Any]:
    return ref.model_dump(mode="json")


def _statement_summary_to_json(s: PassageStatementSummary) -> dict[str, Any]:
    return {
        "statement_text": s.statement_text,
        "span": list(s.span) if s.span is not None else None,
        "interpretation": s.interpretation.value,
        "boundary_confidence": s.boundary_confidence,
        "became_requirement_id": s.became_requirement_id,
        "used_as_supporting_for": list(s.used_as_supporting_for),
    }


def _ledger_entry_to_json(entry: RetrievalLedgerEntry) -> dict[str, Any]:
    return {
        "passage_id": entry.passage_id,
        "originating_question_id": entry.originating_question_id,
        "source_ref": _source_ref_to_json(entry.source_ref),
        "verification_status": entry.verification_status.value,
        "statements": [_statement_summary_to_json(s) for s in entry.statements],
        "detail": entry.detail,
    }


def _write_retrieval_ledger_event(
    engine: Engine,
    *,
    session_id: str,
    started_event_id: str,
    claim_id: str,
    ledger: Sequence[RetrievalLedgerEntry],
) -> str:
    """Persists one claim's retrieval ledger using the existing,
    unmodified write_event() -- action="retrieval_ledger" is a plain
    string value in AuditEvent.action's already-unconstrained column;
    status=COMPLETED records a fact, not an operation needing a separate
    started/terminal pair; parent_event_id links it to the same run
    `started` event every FindingRecord in the run already references."""
    event = AuditEvent(
        session_id=session_id,
        agent_name=AgentName.S6_CONTAINER_CLOSURE,
        action="retrieval_ledger",
        status=EventStatus.COMPLETED,
        parent_event_id=started_event_id,
        detail={
            "claim_id": claim_id,
            "entries": [_ledger_entry_to_json(e) for e in ledger],
        },
    )
    return write_event(engine, event)


# ---------------------------------------------------------------------------
# Rejected-claim audit handling (Phase 5a)
# ---------------------------------------------------------------------------


def _record_claim_rejection(
    engine: Engine,
    *,
    session_id: str,
    started_event_id: str,
    rejection: ParseRejection,
    severity_policy: SeverityPolicy,
    severity_seen: dict[tuple[Verdict, str], Severity],
) -> str | None:
    """Record one parser.ParseRejection in the audit trail.

    A FindingRecord may only be written when the parser has genuinely
    validated a usable claim_id. Only "empty_claim_text",
    "invalid_source_ref" and "wrong_section" ever carry one --
    parser.py only reaches those three checks after BOTH confirming
    isinstance(raw_input, S6Claim) AND validating claim_id itself as
    non-empty -- so those three are recorded as FindingRecords, using
    the claim's own genuine .section/.text/.source_ref fields (one of
    which is the specific thing that failed validation).

    "empty_claim_id" and "invalid_input" never produce a FindingRecord:
    an empty id is not a validated, usable identifier (using None would
    avoid fabricating one, but the approved design calls for an audit
    event instead, not a finding), and an invalid_input was never a
    claim to begin with. Both are recorded as a plain AuditEvent
    instead, via the same write_event() already used for the retrieval
    ledger, with no claim_id ever fabricated.

    Returns the finding id if a FindingRecord was written, else None.
    """
    if rejection.reason in ("invalid_input", "empty_claim_id"):
        detail: dict[str, Any] = {
            "reason": rejection.reason,
            "rejection_detail": rejection.detail,
        }
        if rejection.reason == "invalid_input":
            detail["raw_input_type"] = type(rejection.raw_input).__name__
            detail["raw_input_repr"] = repr(rejection.raw_input)[:500]
        else:
            # empty_claim_id: raw_input IS a genuine S6Claim instance
            # (parser.py only reaches R1 after confirming that) -- it
            # just has no usable id. Its other real fields are safe,
            # non-fabricated audit detail, not a substitute identifier.
            claim = rejection.raw_input
            detail["section"] = getattr(claim, "section", None)
            detail["claim_text"] = getattr(claim, "text", None)
        write_event(
            engine,
            AuditEvent(
                session_id=session_id,
                agent_name=AgentName.S6_CONTAINER_CLOSURE,
                action=f"s6_claim_rejected_{rejection.reason}",
                status=EventStatus.COMPLETED,
                parent_event_id=started_event_id,
                detail=detail,
            ),
        )
        return None

    # R2/R3/R4: a genuine, parser-validated claim_id exists.
    claim = rejection.raw_input
    detail = {
        "evaluation_path": f"claim_rejected_{rejection.reason}",
        "rejection_detail": rejection.detail,
    }
    severity = _assign_severity(
        Verdict.INSUFFICIENT_DATA, detail, severity_policy, seen=severity_seen
    )
    finding = FindingRecord(
        event_id=started_event_id,
        session_id=session_id,
        agent_name=AgentName.S6_CONTAINER_CLOSURE,
        finding_type=FindingType.COMPLIANCE,
        section=claim.section,
        claim_text=claim.text,
        claim_id=rejection.claim_id,
        requirement=None,
        requirement_id=None,
        verdict=Verdict.INSUFFICIENT_DATA,
        severity=severity,
        citation=None,
        rationale=rejection.detail,
        source_refs=[claim.source_ref],
        detail=detail,
    )
    return write_finding(engine, finding)


# ---------------------------------------------------------------------------
# Per-claim regulatory evaluation
# ---------------------------------------------------------------------------


def _evaluate_claim_regulatory(
    claim: S6Claim,
    *,
    evidence_source: RegulatoryEvidenceSource | None,
    question_builder: QuestionBuilder | None,
    source_restriction_verifier: SourceRestrictionVerifier | None,
    passage_interpreter: PassageInterpreterFn | None,
    applicability_classifier: ApplicabilityClassifierFn | None,
    requirement_evidence_linker: RequirementEvidenceLinkerFn | None,
    approved_predicates: Mapping[str, ApprovedPredicate],
    severity_policy: SeverityPolicy,
    severity_seen: dict[tuple[Verdict, str], Severity],
) -> ClaimRegulatoryResult:
    assessments: list[RequirementAssessment] = []
    ledger: list[RetrievalLedgerEntry] = []

    def _add(
        requirement_id: str | None,
        verdict: Verdict,
        rationale: str,
        citation: str | None,
        source_refs: tuple[SourceReference, ...],
        detail: dict[str, Any],
    ) -> None:
        severity = _assign_severity(verdict, detail, severity_policy, seen=severity_seen)
        assessments.append(
            RequirementAssessment(
                claim_id=claim.claim_id,
                requirement_id=requirement_id,
                verdict=verdict,
                severity=severity,
                rationale=rationale,
                citation=citation,
                source_refs=source_refs,
                detail=detail,
            )
        )

    def _finish() -> ClaimRegulatoryResult:
        return ClaimRegulatoryResult(
            claim_id=claim.claim_id,
            assessments=tuple(assessments),
            overall_verdict=_overall_verdict(assessments),
            retrieval_ledger=tuple(ledger),
        )

    if question_builder is None:
        _add(
            None, Verdict.INSUFFICIENT_DATA,
            "No question-building strategy has been supplied; M2 was never queried.",
            None, (claim.source_ref,), {"evaluation_path": "no_question_builder"},
        )
        return _finish()

    if evidence_source is None:
        _add(
            None, Verdict.INSUFFICIENT_DATA,
            "No regulatory evidence source has been supplied; M2 was never queried.",
            None, (claim.source_ref,), {"evaluation_path": "no_evidence_source"},
        )
        return _finish()

    try:
        raw_questions = question_builder(claim)
    except Exception as exc:  # noqa: BLE001
        _add(
            None, Verdict.INSUFFICIENT_DATA,
            "The question-building strategy raised an exception for this claim.",
            None, (claim.source_ref,),
            {
                "evaluation_path": "question_builder_error",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )
        return _finish()

    questions = list(raw_questions) if raw_questions is not None else []
    valid_questions = [q for q in questions if isinstance(q, RegulatoryQuestion) and q.question.strip()]

    if not valid_questions:
        _add(
            None, Verdict.INSUFFICIENT_DATA,
            "The question-building strategy returned no usable question for this claim.",
            None, (claim.source_ref,),
            {"evaluation_path": "no_topics_selected", "raw_question_count": len(questions)},
        )
        return _finish()

    all_passages: list[RetrievedPassage] = []
    failed_questions: list[dict[str, Any]] = []
    for question in valid_questions:
        try:
            raw_passages = evidence_source.search(question)
        except PortError as exc:
            failed_questions.append({"question_id": question.question_id, "error_message": str(exc)})
            continue
        all_passages.extend(raw_passages)

    if not all_passages:
        detail: dict[str, Any] = {}
        if failed_questions and len(failed_questions) == len(valid_questions):
            detail["evaluation_path"] = "requirement_port_unavailable"
        else:
            detail["evaluation_path"] = "no_requirement_returned"
        if failed_questions:
            detail["failed_questions"] = failed_questions
        _add(
            None, Verdict.INSUFFICIENT_DATA,
            "M2 was queried but no retrievable passages were obtained for this claim.",
            None, (claim.source_ref,), detail,
        )
        return _finish()

    # --- fail-closed source restriction gate ---
    dispositions, restriction_detail = _verify_source_restriction(all_passages, source_restriction_verifier)
    verified_passages = [
        p for p in all_passages if dispositions.get(p.passage_id) == SourceVerificationStatus.VERIFIED
    ]
    for p in all_passages:
        status = dispositions.get(p.passage_id, SourceVerificationStatus.UNVERIFIABLE)
        if status != SourceVerificationStatus.VERIFIED:
            ledger.append(
                RetrievalLedgerEntry(
                    passage_id=p.passage_id,
                    originating_question_id=p.originating_question_id,
                    source_ref=p.source_ref,
                    verification_status=status,
                    statements=(),
                    detail=dict(restriction_detail),
                )
            )

    if not verified_passages:
        _add(
            None, Verdict.INSUFFICIENT_DATA,
            "Retrieved evidence could not be verified as belonging to an approved source "
            "category (Pharmacopeial Monographs / Others); it has not been interpreted or "
            "assessed.",
            None, (claim.source_ref,), dict(restriction_detail),
        )
        return _finish()

    # --- interpretation: classify every verified passage into statements ---
    all_statements: list[PassageStatement] = []
    passage_ledger_detail: dict[str, dict[str, Any]] = {}
    for p in verified_passages:
        stmts, idetail = _interpret_passage(p, claim, passage_interpreter)
        passage_ledger_detail[p.passage_id] = idetail
        all_statements.extend(stmts)

    became_requirement: dict[tuple[str, Any, str], str] = {}
    supporting_for: dict[tuple[str, Any, str], list[str]] = {}
    uncertain_count = 0
    excluded_counts: dict[str, int] = {}

    for stmt in all_statements:
        if stmt.interpretation == PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT:
            requirement_id = str(uuid.uuid4())
            pool = [s for s in all_statements if s is not stmt]
            supporting, link_detail = _link_supporting_statements(
                stmt, pool, requirement_evidence_linker
            )
            applicability, app_detail = _classify_applicability(
                stmt.source_passage, claim, applicability_classifier
            )
            requirement = InterpretedRequirement(
                requirement_id=requirement_id,
                text=stmt.statement_text,
                citation=_citation_from_passage(stmt.source_passage),
                primary_statement=stmt,
                applicability=applicability,
                supporting_statements=supporting,
                detail={**link_detail, **app_detail},
            )
            verdict, rationale, pdetail, citation, refs = _evaluate_predicate(
                claim, requirement, approved_predicates
            )
            _add(requirement_id, verdict, rationale, citation, refs, {**requirement.detail, **pdetail})
            became_requirement[_statement_key(stmt)] = requirement_id
            for sup in supporting:
                supporting_for.setdefault(_statement_key(sup), []).append(requirement_id)
        elif stmt.interpretation == PassageInterpretation.UNCERTAIN_INTERPRETATION:
            uncertain_count += 1
            _add(
                None, Verdict.NEEDS_REVIEW,
                "A retrieved statement's role could not be confidently classified as a "
                "requirement, supporting information, or not applicable.",
                None, (claim.source_ref, stmt.source_passage.source_ref),
                {
                    "evaluation_path": "uncertain_passage_interpretation",
                    **passage_ledger_detail.get(stmt.source_passage.passage_id, {}),
                },
            )
        else:
            excluded_counts[stmt.interpretation.value] = excluded_counts.get(stmt.interpretation.value, 0) + 1

    requirement_count = len(became_requirement)

    for p in verified_passages:
        stmts_for_p = [s for s in all_statements if s.source_passage.passage_id == p.passage_id]
        summaries = tuple(
            PassageStatementSummary(
                statement_text=s.statement_text,
                span=s.span,
                interpretation=s.interpretation,
                boundary_confidence=s.boundary_confidence,
                became_requirement_id=became_requirement.get(_statement_key(s)),
                used_as_supporting_for=tuple(supporting_for.get(_statement_key(s), [])),
            )
            for s in stmts_for_p
        )
        ledger.append(
            RetrievalLedgerEntry(
                passage_id=p.passage_id,
                originating_question_id=p.originating_question_id,
                source_ref=p.source_ref,
                verification_status=SourceVerificationStatus.VERIFIED,
                statements=summaries,
                detail=dict(passage_ledger_detail.get(p.passage_id, {})),
            )
        )

    if requirement_count == 0 and uncertain_count == 0:
        _add(
            None, Verdict.INSUFFICIENT_DATA,
            "Verified evidence was retrieved, but none of it was interpreted as a "
            "potentially applicable requirement.",
            None, (claim.source_ref,),
            {"evaluation_path": "no_applicable_requirement_identified", "excluded_counts": excluded_counts},
        )

    return _finish()


# ---------------------------------------------------------------------------
# Cross-section boundary (S7 is never independently converted to a Verdict)
# ---------------------------------------------------------------------------


def _evaluate_cross_section(
    claims: Sequence[S6Claim],
    stability_source: StabilitySource,
    session_id: str,
) -> tuple[LinkResult | None, str]:
    try:
        conditions = stability_source.get_stability_conditions(session_id)
    except PortError:
        return None, "port_unavailable"
    return link_stability_conditions(list(claims), list(conditions)), "ok"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_evaluation(
    engine: Engine,
    *,
    session_id: str,
    claim_source: ClaimSource,
    stability_source: StabilitySource,
    severity_policy: SeverityPolicy,
    evidence_source: RegulatoryEvidenceSource | None = None,
    question_builder: QuestionBuilder | None = None,
    source_restriction_verifier: SourceRestrictionVerifier | None = None,
    passage_interpreter: PassageInterpreterFn | None = None,
    applicability_classifier: ApplicabilityClassifierFn | None = None,
    requirement_evidence_linker: RequirementEvidenceLinkerFn | None = None,
    approved_predicates: Mapping[str, ApprovedPredicate] | None = None,
) -> EvaluationRunResult:
    """Evaluate every S.6 claim in `session_id` for regulatory
    compliance and S.6/S.7 cross-section consistency, persisting
    findings and one retrieval-ledger event per claim through the
    existing, unmodified audit layer.

    `severity_policy` is REQUIRED (no default): the project establishes
    no meaning for Severity, so this module never guesses one (see
    SeverityPolicyError). Every other extension point defaults to the
    safest, most conservative behaviour when omitted -- in particular,
    with no `source_restriction_verifier`, every claim's regulatory
    evidence is fail-closed to INSUFFICIENT_DATA (see module docstring).

    Phase 5a: every raw claim from `claim_source.get_claims()` passes
    through the existing, unmodified `container_closure.parser.parse_claims`
    before evaluation. Only parser-accepted claims proceed through the
    normal evaluation (and S.6/S.7 cross-section) pipeline; every rejected
    claim is recorded in the audit trail via `_record_claim_rejection`
    rather than being silently dropped or evaluated against incomplete
    data.
    """
    predicates: Mapping[str, ApprovedPredicate] = approved_predicates or {}
    severity_seen: dict[tuple[Verdict, str], Severity] = {}

    with execution_scope(
        engine,
        session_id=session_id,
        agent_name=AgentName.S6_CONTAINER_CLOSURE,
        action="s6_evaluate",
    ) as started:
        try:
            raw_claims = claim_source.get_claims(session_id)
        except PortError as exc:
            raise EvaluatorRunAborted(f"ClaimSource.get_claims failed: {exc}") from exc

        parsed = parse_claims(raw_claims)
        claims = parsed.accepted

        finding_ids: list[str] = []
        try:
            for rejection in parsed.rejected:
                finding_id = _record_claim_rejection(
                    engine,
                    session_id=session_id,
                    started_event_id=started.id,
                    rejection=rejection,
                    severity_policy=severity_policy,
                    severity_seen=severity_seen,
                )
                if finding_id is not None:
                    finding_ids.append(finding_id)
        except AuditWriteError as exc:
            raise EvaluatorRunAborted(
                f"audit write failed while recording a rejected claim: {exc}"
            ) from exc

        cross_section, cross_section_status = _evaluate_cross_section(claims, stability_source, session_id)

        regulatory: list[ClaimRegulatoryResult] = []

        for claim in claims:
            result = _evaluate_claim_regulatory(
                claim,
                evidence_source=evidence_source,
                question_builder=question_builder,
                source_restriction_verifier=source_restriction_verifier,
                passage_interpreter=passage_interpreter,
                applicability_classifier=applicability_classifier,
                requirement_evidence_linker=requirement_evidence_linker,
                approved_predicates=predicates,
                severity_policy=severity_policy,
                severity_seen=severity_seen,
            )

            try:
                for assessment in result.assessments:
                    finding = FindingRecord(
                        event_id=started.id,
                        session_id=session_id,
                        agent_name=AgentName.S6_CONTAINER_CLOSURE,
                        finding_type=FindingType.COMPLIANCE,
                        section=claim.section,
                        claim_text=claim.text,
                        claim_id=claim.claim_id,
                        requirement=None,
                        requirement_id=assessment.requirement_id,
                        verdict=assessment.verdict,
                        severity=assessment.severity,
                        citation=assessment.citation,
                        rationale=assessment.rationale,
                        source_refs=list(assessment.source_refs),
                        detail=assessment.detail,
                    )
                    finding_ids.append(write_finding(engine, finding))

                _write_retrieval_ledger_event(
                    engine,
                    session_id=session_id,
                    started_event_id=started.id,
                    claim_id=claim.claim_id,
                    ledger=result.retrieval_ledger,
                )
            except AuditWriteError as exc:
                raise EvaluatorRunAborted(
                    f"audit write failed while processing claim={claim.claim_id}: {exc}"
                ) from exc

            regulatory.append(result)

        return EvaluationRunResult(
            session_id=session_id,
            event_id=started.id,
            regulatory=regulatory,
            cross_section=cross_section,
            cross_section_status=cross_section_status,
            finding_ids=finding_ids,
        )
