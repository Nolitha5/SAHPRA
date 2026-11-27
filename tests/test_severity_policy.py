"""
Tests for container_closure.severity_policy (Phase 5c).

Covers: interface behaviour, complete policy coverage, detection of
missing evaluation paths, no silent default severity for an unknown
path, clear synthetic-only placeholder labelling, and a static
regression check that KNOWN_EVALUATION_PATHS has not drifted from
evaluator.py's own literal "evaluation_path" strings.
"""
from __future__ import annotations

import inspect
import re

import container_closure.evaluator as evaluator_module
import container_closure.parser as parser_module
from shared.enums import Severity, Verdict

from container_closure.severity_policy import (
    KNOWN_EVALUATION_PATHS,
    UnknownEvaluationPathError,
    build_severity_policy,
    check_completeness,
)

# A synthetic, test-only, explicitly labelled placeholder mapping covering
# every known path. These severities carry NO regulatory meaning and are
# never imported or reused outside this test module.
# [SYNTHETIC TEST DATA]
_SYNTHETIC_COMPLETE_MAPPING: dict[str, Severity] = {path: Severity.INFO for path in KNOWN_EVALUATION_PATHS}


# ---------------------------------------------------------------------------
# Interface behaviour
# ---------------------------------------------------------------------------


class TestInterfaceBehaviour:
    def test_built_policy_matches_evaluators_calling_convention(self):
        policy = build_severity_policy(_SYNTHETIC_COMPLETE_MAPPING)

        result = policy(Verdict.COMPLIANT, {"evaluation_path": "predicate_satisfied"})

        assert result is Severity.INFO

    def test_different_known_paths_resolve_independently(self):
        mapping = dict(_SYNTHETIC_COMPLETE_MAPPING)
        mapping["predicate_breached"] = Severity.CRITICAL
        policy = build_severity_policy(mapping)

        assert policy(Verdict.NON_COMPLIANT, {"evaluation_path": "predicate_breached"}) is Severity.CRITICAL
        assert policy(Verdict.COMPLIANT, {"evaluation_path": "predicate_satisfied"}) is Severity.INFO

    def test_policy_does_not_mutate_the_mapping_it_was_built_from(self):
        mapping = dict(_SYNTHETIC_COMPLETE_MAPPING)
        original = dict(mapping)
        policy = build_severity_policy(mapping)
        policy(Verdict.COMPLIANT, {"evaluation_path": "predicate_satisfied"})

        assert mapping == original


# ---------------------------------------------------------------------------
# Complete policy coverage
# ---------------------------------------------------------------------------


class TestCompletePolicyCoverage:
    def test_synthetic_complete_mapping_reports_complete(self):
        report = check_completeness(_SYNTHETIC_COMPLETE_MAPPING)

        assert report.is_complete
        assert report.missing_paths == frozenset()

    def test_build_succeeds_silently_when_mapping_is_complete(self):
        build_severity_policy(_SYNTHETIC_COMPLETE_MAPPING)  # must not raise


# ---------------------------------------------------------------------------
# Detection of missing evaluation paths
# ---------------------------------------------------------------------------


class TestMissingPathDetection:
    def test_check_completeness_reports_a_removed_path_as_missing(self):
        incomplete = dict(_SYNTHETIC_COMPLETE_MAPPING)
        incomplete.pop("predicate_satisfied")

        report = check_completeness(incomplete)

        assert "predicate_satisfied" in report.missing_paths
        assert not report.is_complete

    def test_build_severity_policy_raises_on_incomplete_mapping_by_default(self):
        incomplete = dict(_SYNTHETIC_COMPLETE_MAPPING)
        incomplete.pop("no_predicate")

        try:
            build_severity_policy(incomplete)
            assert False, "expected UnknownEvaluationPathError"
        except UnknownEvaluationPathError as exc:
            assert "no_predicate" in str(exc)

    def test_empty_mapping_reports_every_known_path_missing(self):
        report = check_completeness({})

        assert report.missing_paths == KNOWN_EVALUATION_PATHS

    def test_extra_unknown_keys_are_reported_but_not_an_error(self):
        mapping = dict(_SYNTHETIC_COMPLETE_MAPPING)
        mapping["some_future_path_not_yet_known"] = Severity.MINOR

        report = check_completeness(mapping)

        assert report.is_complete
        assert "some_future_path_not_yet_known" in report.extra_paths


# ---------------------------------------------------------------------------
# No silent default severity for an unknown path
# ---------------------------------------------------------------------------


class TestNoSilentDefaultForUnknownPath:
    def test_policy_built_with_require_complete_false_still_raises_at_call_time(self):
        partial = {"predicate_satisfied": Severity.INFO}
        policy = build_severity_policy(partial, require_complete=False)

        try:
            policy(Verdict.NEEDS_REVIEW, {"evaluation_path": "no_predicate"})
            assert False, "expected UnknownEvaluationPathError"
        except UnknownEvaluationPathError:
            pass

    def test_policy_never_returns_a_default_severity_for_a_totally_unknown_path(self):
        partial = {"predicate_satisfied": Severity.INFO}
        policy = build_severity_policy(partial, require_complete=False)

        try:
            result = policy(Verdict.INSUFFICIENT_DATA, {"evaluation_path": "totally_unknown_path"})
            assert False, f"expected an exception, got a severity instead: {result!r}"
        except UnknownEvaluationPathError:
            pass

    def test_a_missing_evaluation_path_key_entirely_is_also_treated_as_unknown(self):
        partial = {"predicate_satisfied": Severity.INFO}
        policy = build_severity_policy(partial, require_complete=False)

        try:
            policy(Verdict.INSUFFICIENT_DATA, {})
            assert False, "expected an exception"
        except UnknownEvaluationPathError:
            pass


# ---------------------------------------------------------------------------
# Synthetic placeholders are clearly identified; no production content
# ---------------------------------------------------------------------------


class TestSyntheticPlaceholdersAreLabelled:
    def test_production_module_defines_no_severity_mapping_itself(self):
        # severity_policy.py ships with zero built-in (path -> Severity)
        # content: an empty mapping must be missing every known path.
        assert check_completeness({}).missing_paths == KNOWN_EVALUATION_PATHS

    def test_this_modules_placeholder_mapping_is_non_empty_real_coverage(self):
        # Sanity check that the test-local synthetic mapping actually
        # covers something, rather than being an empty stub.
        assert _SYNTHETIC_COMPLETE_MAPPING
        assert all(isinstance(v, Severity) for v in _SYNTHETIC_COMPLETE_MAPPING.values())


# ---------------------------------------------------------------------------
# Static drift detection: KNOWN_EVALUATION_PATHS vs. evaluator.py's source
# ---------------------------------------------------------------------------


class TestKnownPathsMatchEvaluatorSource:
    def test_static_scan_of_evaluator_source_matches_known_paths(self):
        src = inspect.getsource(evaluator_module)

        found: set[str] = set()
        for m in re.finditer(r'"evaluation_path"\s*:\s*"([a-z_]+)"', src):
            found.add(m.group(1))
        for m in re.finditer(r'detail\["evaluation_path"\]\s*=\s*"([a-z_]+)"', src):
            found.add(m.group(1))
        for m in re.finditer(r'^\s{4,}path = "([a-z_]+)"\s*$', src, re.MULTILINE):
            found.add(m.group(1))
        for m in re.finditer(r'^\s*(?:else\s+)?"([a-z_]+)"\s*$', src, re.MULTILINE):
            found.add(m.group(1))

        # These two exist under the DIFFERENT key name
        # "linker_evaluation_path", which _assign_severity never reads --
        # deliberately excluded from KNOWN_EVALUATION_PATHS (see that
        # module's docstring). Strip them so this comparison is like-for-like.
        found -= {"linker_error", "linker_invalid_result"}

        dynamic_paths = {
            "claim_rejected_empty_claim_text",
            "claim_rejected_invalid_source_ref",
            "claim_rejected_wrong_section",
        }

        expected = found | dynamic_paths

        assert expected == KNOWN_EVALUATION_PATHS, (
            "evaluator.py's literal evaluation_path strings have drifted from "
            "severity_policy.KNOWN_EVALUATION_PATHS.\n"
            f"In evaluator.py but missing from KNOWN_EVALUATION_PATHS: "
            f"{sorted(expected - KNOWN_EVALUATION_PATHS)}\n"
            f"In KNOWN_EVALUATION_PATHS but not found in evaluator.py: "
            f"{sorted(KNOWN_EVALUATION_PATHS - expected)}"
        )

    def test_claim_rejected_reachable_reasons_match_parsers_own_reason_codes(self):
        # Confirm, by reading _record_claim_rejection's own source, that
        # exactly the reasons we hardcoded as audit-event-only are excluded
        # from the FindingRecord-creating (severity-calling) branch.
        eval_src = inspect.getsource(evaluator_module._record_claim_rejection)
        m = re.search(r"rejection\.reason in \(([^)]+)\)", eval_src)
        assert m is not None, "expected an explicit reason-exclusion tuple in _record_claim_rejection"
        excluded = {part.strip().strip('"').strip("'") for part in m.group(1).split(",") if part.strip()}
        assert excluded == {"invalid_input", "empty_claim_id"}

        # Confirm the full set of reason codes the parser actually defines,
        # read from its own module-level _REASON_* constants.
        parser_src = inspect.getsource(parser_module)
        all_reasons = set(re.findall(r'_REASON_[A-Z_]+\s*=\s*"([a-z_]+)"', parser_src))
        assert all_reasons, "could not statically find any parser _REASON_* literals in parser.py"

        reachable = all_reasons - excluded
        expected_claim_rejected_paths = {f"claim_rejected_{r}" for r in reachable}

        assert expected_claim_rejected_paths == {
            "claim_rejected_empty_claim_text",
            "claim_rejected_invalid_source_ref",
            "claim_rejected_wrong_section",
        }
