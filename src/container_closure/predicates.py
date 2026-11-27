"""
Citation-keyed predicate registry for the S.6 Container Closure Agent
(Phase 5c).

Implements container_closure.evaluator.ApprovedPredicate:
    Callable[[S6Claim, InterpretedRequirement], PredicateAssessment]

and a Mapping[str, ApprovedPredicate]-compatible object that lets
evaluator.py consume this registry completely unchanged.

The gap this resolves
----------------------
evaluator.py's only predicate lookup is, verbatim (_evaluate_predicate):

    predicate = predicates.get(requirement.requirement_id)

`InterpretedRequirement.requirement_id` is a FRESH `uuid.uuid4()`
generated once per promotion inside `_evaluate_claim_regulatory`
(evaluator.py) -- it is not stable, not reusable, and not knowable in
advance. No static {requirement_id: predicate} mapping could ever be
populated ahead of time against it; a registry keyed that way would be
permanently empty by construction.

`InterpretedRequirement.citation`, by contrast, is produced
deterministically from the retrieved passage's own stable fields
(`_citation_from_passage`) and is exactly what the approved Phase 5c
design calls for as the predicate dispatch key.

Resolution: a "wildcard" Mapping shim. `_evaluate_predicate` calls
`predicates.get(requirement.requirement_id)` and then calls whatever
it gets back as `predicate(claim, requirement)` -- the SAME
`requirement` object is passed to the predicate call itself. So the
shim ignores the (random, unusable) key it is asked for and always
returns the SAME dispatcher callable; that dispatcher, once actually
invoked with `(claim, requirement)`, reads the one piece of real,
stable, caller-controlled information it has -- `requirement.citation`
-- and performs the genuine citation-keyed lookup at that point. The
Mapping's `__getitem__`/`get` therefore always succeeds (never raises
KeyError, never falls back to evaluator.py's own built-in
"no_predicate" NEEDS_REVIEW path) for any key it is asked about; all of
the real dispatch decision happens one call-frame later, inside the
dispatcher, where `requirement.citation` is actually available.
Citation lookup itself is a single exact dict-key lookup -- never
keyword matching, text similarity, or passage-wording inference.

What this is NOT
-----------------
* Not a source of real regulatory predicates. This module defines the
  registry and dispatch mechanism only; it registers nothing by
  default. Any predicate function used in this project's tests is
  placeholder data, explicitly labelled `[SYNTHETIC TEST DATA]`,
  confined to tests/test_predicates.py, and carries no regulatory
  authority.
* Not a change to evaluator.py or any of its existing interfaces --
  `ApprovedPredicate`, `PredicateAssessment`, `PredicateOutcome`, and
  `InterpretedRequirement` are all imported unchanged, and
  `_evaluate_predicate`'s single call site needs no modification for
  this registry to work.
* Not a heuristic matcher. An unresolved citation always and only
  resolves to PredicateOutcome.INDETERMINATE; nothing here ever reads
  passage text, claim text, or keyword overlap to reach SATISFIED or
  BREACHED.
"""
from __future__ import annotations

from collections.abc import Mapping as ABCMapping
from typing import Iterator, Mapping

from shared.models import S6Claim

from container_closure.evaluator import (
    ApprovedPredicate,
    InterpretedRequirement,
    PredicateAssessment,
    PredicateOutcome,
)


class CitationPredicateRegistry:
    """A plain citation -> ApprovedPredicate registry. Holds no
    production content by default -- starts empty, and stays empty
    unless a caller explicitly registers something (see module
    docstring, "What this is NOT")."""

    def __init__(self, predicates: Mapping[str, ApprovedPredicate] | None = None) -> None:
        self._by_citation: dict[str, ApprovedPredicate] = dict(predicates) if predicates else {}

    def register(self, citation: str, predicate: ApprovedPredicate) -> None:
        if not isinstance(citation, str) or not citation.strip():
            raise ValueError("citation must be a non-empty string")
        self._by_citation[citation] = predicate

    def resolve(self, citation: str | None) -> ApprovedPredicate | None:
        """Exact-match lookup only. A missing citation (None) and any
        citation string that is simply not registered both return
        None -- never a heuristic fallback, never a partial match."""
        if citation is None:
            return None
        return self._by_citation.get(citation)

    def citations(self) -> frozenset[str]:
        return frozenset(self._by_citation)

    def __len__(self) -> int:
        return len(self._by_citation)

    def __contains__(self, citation: object) -> bool:
        return citation in self._by_citation

    def as_mapping(self) -> Mapping[str, ApprovedPredicate]:
        """The Mapping[str, ApprovedPredicate]-compatible object to
        pass as run_evaluation(..., approved_predicates=...). See
        module docstring, "Resolution: a 'wildcard' Mapping shim."
        """
        return _WildcardCitationMapping(self)


def resolve_predicate(
    claim: S6Claim,
    requirement: InterpretedRequirement,
    *,
    registry: CitationPredicateRegistry,
) -> PredicateAssessment:
    """The actual citation-keyed dispatch, directly unit-testable
    without going through the Mapping shim. Looks up
    `requirement.citation` (never `requirement.requirement_id`) in
    `registry`. An unregistered citation always resolves to
    PredicateOutcome.INDETERMINATE; no exception is raised here and no
    conclusive outcome is ever invented."""
    impl = registry.resolve(requirement.citation)
    if impl is None:
        return PredicateAssessment(
            outcome=PredicateOutcome.INDETERMINATE,
            rationale=(
                f"No approved predicate is registered for citation "
                f"{requirement.citation!r}. Citation-based dispatch could "
                f"not resolve this requirement; resolving to INDETERMINATE "
                f"rather than inventing a judgement."
            ),
            detail={"unresolved_citation": requirement.citation, "dispatch": "citation_not_registered"},
        )
    return impl(claim, requirement)


class _WildcardCitationMapping(ABCMapping):
    """Mapping[str, ApprovedPredicate]-compatible shim. See module
    docstring. Every key -- however it is asked for, including the
    random `requirement.requirement_id` that evaluator.py actually
    passes to `.get()` -- resolves to the SAME dispatcher callable; the
    dispatcher performs the real citation-keyed lookup only once it is
    actually invoked with `(claim, requirement)`.

    `__bool__` is always True regardless of how many citations are
    registered: evaluator.py's run_evaluation does
    `predicates = approved_predicates or {}`, and an EMPTY registry
    must still activate wildcard dispatch (so that every requirement
    correctly resolves to INDETERMINATE via the dispatcher) rather than
    silently falling back to evaluator.py's own bare `{}` default,
    which produces a different, undispatched "no_predicate" /
    NEEDS_REVIEW outcome instead.
    """

    def __init__(self, registry: CitationPredicateRegistry) -> None:
        self._registry = registry

    def __getitem__(self, _requirement_id: str) -> ApprovedPredicate:
        def _dispatch(claim: S6Claim, requirement: InterpretedRequirement) -> PredicateAssessment:
            return resolve_predicate(claim, requirement, registry=self._registry)

        return _dispatch

    def __iter__(self) -> Iterator[str]:
        return iter(self._registry.citations())

    def __len__(self) -> int:
        return len(self._registry)

    def __bool__(self) -> bool:
        return True
