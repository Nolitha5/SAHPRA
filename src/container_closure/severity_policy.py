"""
SeverityPolicy completeness framework for the S.6 Container Closure
Agent (Phase 5c).

Implements the test-only completeness-checking framework for
container_closure.evaluator.SeverityPolicy:
    Callable[[Verdict, dict[str, Any]], Severity]

Responsibility
--------------
This module does NOT assign real regulatory severities to anything. It
provides:

1. KNOWN_EVALUATION_PATHS -- a complete, hand-verified, line-cited
   enumeration of every literal "evaluation_path" string evaluator.py
   (Phase 4c/5a) can ever pass to a SeverityPolicy via
   `_assign_severity`, including the three `claim_rejected_<reason>`
   values that are actually reachable (see "Reachability notes"
   below). tests/test_severity_policy.py statically re-scans
   evaluator.py's own source and asserts it matches this set exactly,
   so this list cannot silently go stale.
2. check_completeness(mapping) -- reports exactly which of those known
   paths a caller-supplied {evaluation_path: Severity} mapping is
   missing. Pure, read-only introspection; it mutates nothing and
   never assigns a severity itself.
3. build_severity_policy(mapping) -- wraps a caller-supplied mapping
   into a SeverityPolicy callable. For any evaluation_path NOT present
   in the mapping -- known or not -- it raises
   UnknownEvaluationPathError rather than silently returning a default
   Severity. evaluator.py's own `_assign_severity` already catches any
   exception a SeverityPolicy raises and wraps it as
   SeverityPolicyError, aborting the run via the existing, unmodified
   execution_scope failed-event handling. No evaluator.py change is
   required or made.

What this is NOT
-----------------
* Not a source of real severities. No production
  (evaluation_path -> Severity) mapping is defined anywhere in this
  module -- it ships registering nothing (see
  tests/test_severity_policy.py::
  TestSyntheticPlaceholdersAreLabelled::
  test_production_module_defines_no_severity_mapping_itself). Any such
  mapping used in this project's tests is placeholder data, explicitly
  labelled `[SYNTHETIC TEST DATA]`, confined to
  tests/test_severity_policy.py, and carries no regulatory authority.
* Not a predicate, requirement, or applicability decision of any kind.
* Not a change to evaluator.py's SeverityPolicy contract -- the
  callable this module builds has exactly the signature evaluator.py
  already expects and requires no caller-side change.

Reachability notes (read directly from evaluator.py, not guessed)
-------------------------------------------------------------------
* Every literal in KNOWN_EVALUATION_PATHS below is transcribed from an
  actual `"evaluation_path"` dict-literal key, a
  `detail["evaluation_path"] = ...` assignment, or a local
  `path = "..."` assignment later read into that same key, in
  evaluator.py.
* `claim_rejected_<reason>` is a DYNAMIC f-string
  (evaluator.py, `_record_claim_rejection`). Of the five parser
  rejection reasons (empty_claim_id, empty_claim_text,
  invalid_source_ref, wrong_section, invalid_input), only
  empty_claim_text, invalid_source_ref and wrong_section ever reach
  the FindingRecord-creating branch that calls a SeverityPolicy --
  empty_claim_id and invalid_input are deliberately audit-event-only
  (Phase 5a correction) and never call `_assign_severity` at all. Only
  those three expansions are included below; this is itself
  re-verified statically by
  tests/test_severity_policy.py::
  TestKnownPathsMatchEvaluatorSource::
  test_claim_rejected_reachable_reasons_match_parsers_own_reason_codes.
* Two further literals exist in evaluator.py under the DIFFERENT key
  name "linker_evaluation_path" (`linker_error`, `linker_invalid_result`,
  in `_link_supporting_statements`). They are never read by
  `_assign_severity` (which only ever reads the `"evaluation_path"`
  key) and so are deliberately NOT included here -- including them
  would wrongly claim severity-completeness over a key the evaluator
  never actually dispatches on.
* Several literals here are, in today's evaluator.py, always
  overridden by a later dict-merge before they could ever reach
  `_assign_severity` as the FINAL evaluation_path for a given finding.
  For example, at the "uncertain_passage_interpretation" call site,
  the dict literal also merges in `_interpret_passage`'s own detail
  afterwards, and that detail always carries its own
  "evaluation_path" key, which wins; likewise
  "source_restriction_partially_verified" and
  "source_restriction_fully_verified" can only arise when at least one
  passage WAS verified, which is exactly the condition under which the
  one call site that would use them is skipped entirely. This module
  still requires policy coverage for all of them: requiring a severity
  entry for a path that happens to be unreachable today is harmless,
  whereas omitting one that is (or later becomes) reachable is exactly
  the silent gap this module exists to prevent. This is a deliberate,
  documented, safe-superset choice, not an oversight.
* This project's evaluator.py never pairs the same evaluation_path
  literal with more than one different Verdict at different call
  sites (confirmed by inspection of every call site). This module
  therefore keys its registry by evaluation_path alone, not by
  (Verdict, evaluation_path). If evaluator.py is ever changed so that
  one evaluation_path can arise under more than one Verdict with a
  different intended severity, this module's keying would need
  re-examining -- flagged here rather than silently assumed to still
  hold.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from shared.enums import Severity, Verdict
from shared.exceptions import S6BaseError

from container_closure.evaluator import SeverityPolicy

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class UnknownEvaluationPathError(S6BaseError):
    """Raised by a policy built with build_severity_policy() when asked
    for a severity for an evaluation_path that is not present in the
    mapping it was built from (or, with require_complete=True, raised
    up front if the mapping does not cover every known path at all).
    Never caught inside this module -- evaluator.py's own
    `_assign_severity` already catches any exception a SeverityPolicy
    raises and wraps it as SeverityPolicyError, aborting the run. No
    default severity is ever substituted here."""


# ---------------------------------------------------------------------------
# The known-path enumeration (see module docstring, "Reachability notes")
# ---------------------------------------------------------------------------

KNOWN_EVALUATION_PATHS: frozenset[str] = frozenset(
    {
        # --- run_evaluation / _evaluate_claim_regulatory top-level gates ---
        "no_question_builder",
        "no_evidence_source",
        "question_builder_error",
        "no_topics_selected",
        "requirement_port_unavailable",
        "no_requirement_returned",
        "no_applicable_requirement_identified",
        "uncertain_passage_interpretation",
        # --- _verify_source_restriction (fail-closed gate) ---
        "source_restriction_duplicate_input_ids",
        "source_restriction_unverifiable_no_verifier",
        "source_restriction_verifier_error",
        "source_restriction_verifier_invalid_result",
        "source_restriction_none_verified",
        "source_restriction_partially_verified",
        "source_restriction_fully_verified",
        # --- _interpret_passage ---
        "no_passage_interpreter",
        "passage_interpreter_error",
        "passage_interpreter_invalid_result",
        "passage_interpreter_empty_result",
        "passage_interpreted",
        # --- _classify_applicability (feeds requirement.detail) ---
        "no_applicability_classifier",
        "applicability_classifier_error",
        "applicability_classifier_invalid_result",
        # --- _evaluate_predicate ---
        "no_predicate",
        "predicate_error",
        "predicate_invalid_result",
        "predicate_indeterminate",
        "predicate_missing_evidence",
        "requirement_boundary_uncertain",
        "predicate_satisfied_without_evidence",
        "predicate_breached_without_evidence",
        "predicate_satisfied",
        "predicate_breached",
        # --- _record_claim_rejection (Phase 5a); dynamic f-string, only the
        # three reasons that reach the FindingRecord-creating branch ---
        "claim_rejected_empty_claim_text",
        "claim_rejected_invalid_source_ref",
        "claim_rejected_wrong_section",
    }
)


# ---------------------------------------------------------------------------
# Completeness check
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompletenessReport:
    """Result of check_completeness(). `is_complete` is True iff
    `missing_paths` is empty. `extra_paths` lists entries the mapping
    carries that are not in KNOWN_EVALUATION_PATHS -- never an error by
    itself (a caller may legitimately prepare for a future path), but
    surfaced for visibility rather than silently discarded."""

    missing_paths: frozenset[str]
    extra_paths: frozenset[str]

    @property
    def is_complete(self) -> bool:
        return not self.missing_paths


def check_completeness(
    mapping: Mapping[str, Severity],
    *,
    known_paths: frozenset[str] = KNOWN_EVALUATION_PATHS,
) -> CompletenessReport:
    """Report which of `known_paths` are missing from `mapping`, and
    which of `mapping`'s own keys are not in `known_paths`. Pure,
    read-only introspection -- never raises, never mutates `mapping`,
    never assigns a severity."""
    mapping_keys = frozenset(mapping.keys())
    return CompletenessReport(
        missing_paths=known_paths - mapping_keys,
        extra_paths=mapping_keys - known_paths,
    )


# ---------------------------------------------------------------------------
# SeverityPolicy construction -- no silent default, ever
# ---------------------------------------------------------------------------


def build_severity_policy(
    mapping: Mapping[str, Severity],
    *,
    require_complete: bool = True,
) -> SeverityPolicy:
    """Build a SeverityPolicy callable backed by `mapping`
    (evaluation_path -> Severity).

    If `require_complete` is True (the default), raises
    UnknownEvaluationPathError immediately -- before returning any
    callable -- if `mapping` does not cover every path in
    KNOWN_EVALUATION_PATHS. This stops a severity policy with silent
    gaps from ever being wired into run_evaluation() in the first
    place, rather than discovering the gap only when a particular path
    happens to occur in a real run.

    Regardless of `require_complete`, the returned callable never
    assigns a default Severity for a path it was not given: at call
    time, `(verdict, detail) -> detail.get("evaluation_path", "")`; a
    path not present in `mapping` raises UnknownEvaluationPathError,
    which evaluator.py's own `_assign_severity` already catches and
    wraps as SeverityPolicyError, aborting the run.
    """
    if require_complete:
        report = check_completeness(mapping)
        if not report.is_complete:
            raise UnknownEvaluationPathError(
                f"severity mapping is missing {len(report.missing_paths)} of "
                f"{len(KNOWN_EVALUATION_PATHS)} known evaluation paths: "
                f"{sorted(report.missing_paths)}"
            )

    frozen_mapping: dict[str, Severity] = dict(mapping)

    def _policy(verdict: Verdict, detail: dict[str, Any]) -> Severity:
        # `verdict` is accepted (and required, to match evaluator.py's
        # SeverityPolicy signature exactly) but not used for dispatch --
        # see module docstring's keying note.
        del verdict
        path = detail.get("evaluation_path", "")
        severity = frozen_mapping.get(path)
        if severity is None:
            raise UnknownEvaluationPathError(
                f"no severity is registered for evaluation_path={path!r}; "
                f"refusing to silently assign a default severity"
            )
        return severity

    return _policy
