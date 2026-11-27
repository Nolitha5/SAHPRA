"""
ApplicabilityClassifier for the S.6 Container Closure Agent (Phase 5b).

Implements container_closure.evaluator.ApplicabilityClassifierFn:
    Callable[[RetrievedPassage, S6Claim], ApplicabilityConfidence]

Three decisions, kept structurally separate
---------------------------------------------
1. Source approval -- whether a passage's provenance belongs to an
   approved collection. This module NEVER makes or re-opens that
   decision. It is handled exclusively, upstream, by the existing
   SourceRestrictionVerifier (container_closure.evaluator) before a
   passage ever reaches interpretation or applicability classification
   at all -- run_evaluation only ever passes already-VERIFIED passages
   forward. This module has no parameter through which source-category
   information could even reach it.

2. General relevance to S.6 subject matter -- whether a passage's
   content concerns container-closure topics at all, independent of
   any specific claim. See `_assess_general_s6_relevance`.

3. Applicability to the individual sponsor claim -- the claim-specific
   judgement this module's public function returns, via the
   ApplicabilityConfidence enum. See `_assess_claim_specific_applicability`.

Steps 2 and 3 are kept as separate, independently-testable internal
functions, composed by `classify_applicability` into the single
ApplicabilityConfidence value the existing ApplicabilityClassifierFn
signature requires. Until pharmacist-approved criteria exist for
EITHER step, both internal functions return None ("unknown") for
every input, and the public function therefore always returns
ApplicabilityConfidence.UNCERTAIN. This module invents no applicability
criteria of its own, and never guesses in their absence.

M2's own `RegulatoryQuestion.applicability_statuses` request filter
(evaluator.py) is a retrieval-time, source-status concept belonging
entirely to M2's contract. It is never read, inferred from, or
substituted for the claim-specific judgement made here -- indeed this
module's functions take a RetrievedPassage, which carries no such
field at all, so there is nothing to confuse it with by construction.
"""
from __future__ import annotations

from shared.models import S6Claim

from container_closure.evaluator import ApplicabilityConfidence, RetrievedPassage


def _assess_general_s6_relevance(passage: RetrievedPassage) -> bool | None:  # noqa: ARG001
    """Whether `passage` concerns S.6 container-closure subject matter
    at all, independent of any specific claim.

    Returns None ("unknown") until approved general-relevance criteria
    exist. This module invents none; a future, separately-authorised
    phase may supply real criteria here without changing this
    function's signature or the public classify_applicability
    function's external behaviour until that happens."""
    return None


def _assess_claim_specific_applicability(
    passage: RetrievedPassage, claim: S6Claim  # noqa: ARG001
) -> bool | None:
    """Whether `passage` applies to this specific sponsor claim, given
    that source approval and general S.6 relevance are established
    elsewhere.

    Returns None ("unknown") until approved claim-specific
    applicability criteria exist. This module invents none."""
    return None


def classify_applicability(passage: RetrievedPassage, claim: S6Claim) -> ApplicabilityConfidence:
    """ApplicabilityClassifierFn implementation.

    Composition rule (for when real criteria eventually exist):
    DIRECTLY_RELEVANT requires both general relevance and claim-specific
    applicability to be confirmed (True); POSSIBLY_RELEVANT requires
    general relevance confirmed but claim-specific applicability still
    unknown; every other combination -- including today's actual
    state, where both steps always return None -- resolves to
    UNCERTAIN. No case here ever returns a confidence by guessing.
    """
    general = _assess_general_s6_relevance(passage)
    specific = _assess_claim_specific_applicability(passage, claim)

    if general is True and specific is True:
        return ApplicabilityConfidence.DIRECTLY_RELEVANT
    if general is True and specific is None:
        return ApplicabilityConfidence.POSSIBLY_RELEVANT
    return ApplicabilityConfidence.UNCERTAIN
