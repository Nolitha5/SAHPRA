"""
PassageInterpreter for the S.6 Container Closure Agent (Phase 5b).

Implements container_closure.evaluator.PassageInterpreterFn via the
factory:

    build_passage_interpreter(rules: InterpretationRuleset | None = None)
        -> PassageInterpreterFn

Scope and conservatism
-----------------------
This module ships NO built-in regulatory vocabulary, NO pharmacopoeial
heading taxonomy, and NO default classification rules of any kind.
`InterpretationRuleset` is a purely local configuration container: a
caller supplies whatever pharmacist-approved patterns it has decided
on, and this module applies only those, exactly as given. With
`rules=None` (today's only currently-possible production state, since
no approved ruleset exists yet) -- and also with a ruleset that
carries no patterns in any category -- every identified statement
resolves to UNCERTAIN_INTERPRETATION, with no exception for
strongly normative-looking text. Recognising a word like "shall",
"must", or "should" is never, by itself, sufficient to classify a
statement as an applicable requirement; this module does not look for
such words at all unless a caller's own ruleset explicitly supplies
them as patterns, and even then a statement is only ever classified
with "confident" boundary when it matches exactly one of the three
pattern categories unambiguously -- any zero-match or cross-category
match falls back to UNCERTAIN_INTERPRETATION rather than guessing.

Any InterpretationRuleset used in this module's own tests is synthetic
test data for exercising the classification MECHANISM only. It is not,
and must never be presented as, a validated or pharmacist-approved
regulatory interpretation. Wiring a real ruleset into a production
evaluation run is a decision for a later, separately authorised phase.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from shared.models import S6Claim

from container_closure.evaluator import (
    PassageInterpretation,
    PassageInterpreterFn,
    PassageStatement,
    RetrievedPassage,
)

_SENTENCE_SPLIT_RE = re.compile(r"[^.;\n]+")


@dataclass(frozen=True)
class InterpretationRuleset:
    """Local, caller-supplied classification configuration. Every
    field is a tuple of plain substrings (case-insensitive match); the
    caller decides their content, this module invents none of it.

    An empty ruleset (the default -- no patterns in any category)
    behaves identically to rules=None: every statement resolves to
    UNCERTAIN_INTERPRETATION.
    """

    requirement_patterns: tuple[str, ...] = ()
    not_applicable_patterns: tuple[str, ...] = ()
    supporting_information_patterns: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not (
            self.requirement_patterns
            or self.not_applicable_patterns
            or self.supporting_information_patterns
        )


def _split_statements(text: str) -> list[tuple[str, tuple[int, int]]]:
    """Split `text` into trimmed candidate statements, each paired with
    its exact (start, end) character span in `text` -- so that
    text[start:end] == the trimmed statement, satisfying evaluator.py's
    own span-validation rules."""
    results: list[tuple[str, tuple[int, int]]] = []
    for match in _SENTENCE_SPLIT_RE.finditer(text):
        raw = match.group(0)
        stripped = raw.strip()
        if not stripped:
            continue
        offset = raw.index(stripped)
        start = match.start() + offset
        end = start + len(stripped)
        results.append((stripped, (start, end)))
    return results


def _classify(text: str, rules: InterpretationRuleset) -> tuple[PassageInterpretation, str]:
    """Returns (interpretation, boundary_confidence). Falls back to
    UNCERTAIN_INTERPRETATION / "uncertain" whenever the match is not a
    clean, single-category match -- never guesses between competing
    categories and never treats a bare pattern hit as "confident" on
    its own."""
    lowered = text.lower()
    matched_requirement = any(p.lower() in lowered for p in rules.requirement_patterns)
    matched_not_applicable = any(p.lower() in lowered for p in rules.not_applicable_patterns)
    matched_supporting = any(p.lower() in lowered for p in rules.supporting_information_patterns)

    matched_count = sum([matched_requirement, matched_not_applicable, matched_supporting])
    if matched_count != 1:
        return PassageInterpretation.UNCERTAIN_INTERPRETATION, "uncertain"
    if matched_not_applicable:
        return PassageInterpretation.NOT_APPLICABLE, "confident"
    if matched_supporting:
        return PassageInterpretation.SUPPORTING_INFORMATION, "confident"
    return PassageInterpretation.POTENTIALLY_APPLICABLE_REQUIREMENT, "confident"


def build_passage_interpreter(rules: InterpretationRuleset | None = None) -> PassageInterpreterFn:
    """Build a PassageInterpreterFn bound to `rules`.

    With rules=None or an empty ruleset, the returned function always
    classifies the whole passage as a single UNCERTAIN_INTERPRETATION
    statement (or returns [] for an empty/whitespace-only passage,
    which evaluator.py's own fallback handling already covers). With a
    non-empty ruleset, the returned function splits the passage into
    candidate statements and classifies each one per `_classify`,
    using only the patterns the ruleset explicitly supplies.
    """

    def _interpret_no_rules(passage: RetrievedPassage, claim: S6Claim) -> list[PassageStatement]:  # noqa: ARG001
        if not passage.text.strip():
            return []
        return [
            PassageStatement(
                statement_text=passage.text,
                source_passage=passage,
                interpretation=PassageInterpretation.UNCERTAIN_INTERPRETATION,
                boundary_confidence="uncertain",
                span=None,
            )
        ]

    def _interpret_with_rules(passage: RetrievedPassage, claim: S6Claim) -> list[PassageStatement]:  # noqa: ARG001
        statements: list[PassageStatement] = []
        for stmt_text, span in _split_statements(passage.text):
            interpretation, confidence = _classify(stmt_text, rules)  # type: ignore[arg-type]
            statements.append(
                PassageStatement(
                    statement_text=stmt_text,
                    source_passage=passage,
                    interpretation=interpretation,
                    boundary_confidence=confidence,
                    span=span,
                )
            )
        return statements

    if rules is None or rules.is_empty():
        return _interpret_no_rules
    return _interpret_with_rules
