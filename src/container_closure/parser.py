"""
S.6 Claim Parser for the Container Closure Agent.

Responsibility
--------------
Receive a raw sequence of S6Claim objects (as produced by M3 and
supplied through ClaimSource), validate each one is structurally
complete enough for downstream evaluation, and return a
ParsedClaimSet that separates usable claims from rejected ones.

This module does NOT:
* Evaluate compliance against any regulatory requirement.
* Retrieve anything from M2 or M4b.
* Generate audit events (the agent orchestrator in agent.py does that).
* Invent or supplement missing regulatory content.

Validation rules (deterministic, no LLM)
-----------------------------------------
A claim is REJECTED if it fails any of the following hard checks:

  R1  claim_id is empty or whitespace-only.
  R2  text is empty or whitespace-only.
  R3  source_ref is absent or its source_id / source_type are
      empty / whitespace-only.
  R4  section does not start with "S." (guard against mis-routed
      claims from other dossier sections).

A claim that passes all hard checks is ACCEPTED even if optional
fields (batch_numbers, packaging_components, etc.) are absent.
Absent optional fields result in INSUFFICIENT_DATA findings during
evaluation -- that is the evaluator's concern, not the parser's.

A completely unparseable input (not an S6Claim at all) produces a
single ParseRejection with reason "invalid_input".

No claim is ever silently dropped.  Every input produces either an
accepted claim or a ParseRejection with a human-readable reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from shared.models import S6Claim


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParseRejection:
    """A single claim that could not be accepted for evaluation.

    Attributes
    ----------
    claim_id:
        The claim_id from the input object, or "<unknown>" if it
        could not be extracted.
    reason:
        Machine-readable rejection code (see _REJECTION_CODES below).
    detail:
        Human-readable explanation, suitable for an audit rationale.
    raw_input:
        The original input value, preserved for traceability.  May be
        any type if the input was not a valid S6Claim.
    """
    claim_id: str
    reason: str
    detail: str
    raw_input: Any


@dataclass
class ParsedClaimSet:
    """The output of parse_claims().

    Attributes
    ----------
    accepted:
        Claims that passed all hard validation checks and are ready
        for evaluation.
    rejected:
        Claims that failed one or more hard checks.  The evaluator
        must produce a NEEDS_REVIEW or INSUFFICIENT_DATA finding for
        each rejected claim so it is visible in the audit trail.
    """
    accepted: list[S6Claim] = field(default_factory=list)
    rejected: list[ParseRejection] = field(default_factory=list)

    @property
    def has_accepted(self) -> bool:
        return bool(self.accepted)

    @property
    def total_input_count(self) -> int:
        return len(self.accepted) + len(self.rejected)


# ---------------------------------------------------------------------------
# Rejection reason codes
# ---------------------------------------------------------------------------

_REASON_EMPTY_ID = "empty_claim_id"
_REASON_EMPTY_TEXT = "empty_claim_text"
_REASON_BAD_SOURCE_REF = "invalid_source_ref"
_REASON_WRONG_SECTION = "wrong_section"
_REASON_INVALID_INPUT = "invalid_input"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_claims(raw_claims: Sequence[Any]) -> ParsedClaimSet:
    """Validate and filter a sequence of S6Claim objects.

    Parameters
    ----------
    raw_claims:
        Any sequence.  Elements that are not S6Claim instances
        produce a ParseRejection with reason ``invalid_input``.

    Returns
    -------
    ParsedClaimSet
        Never raises; every input item appears in exactly one of
        ``accepted`` or ``rejected``.
    """
    result = ParsedClaimSet()

    for item in raw_claims:
        rejection = _validate(item)
        if rejection is not None:
            result.rejected.append(rejection)
        else:
            # item is guaranteed to be a valid S6Claim at this point
            result.accepted.append(item)  # type: ignore[arg-type]

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate(item: Any) -> ParseRejection | None:
    """Return a ParseRejection if ``item`` fails any hard check,
    or None if it is acceptable.

    Checks are evaluated in order; the first failure is returned
    immediately (fail-fast).
    """
    # Must be an S6Claim instance
    if not isinstance(item, S6Claim):
        raw_id = "<unknown>"
        try:
            raw_id = str(item.claim_id) if hasattr(item, "claim_id") else "<unknown>"
        except Exception:  # noqa: BLE001
            pass
        return ParseRejection(
            claim_id=raw_id,
            reason=_REASON_INVALID_INPUT,
            detail=(
                f"Input is not an S6Claim instance (got {type(item).__name__!r}). "
                "Cannot evaluate a claim that does not conform to the S6Claim contract."
            ),
            raw_input=item,
        )

    # R1: claim_id must be non-empty
    if not item.claim_id or not item.claim_id.strip():
        return ParseRejection(
            claim_id="<empty>",
            reason=_REASON_EMPTY_ID,
            detail="claim_id is empty or whitespace-only. Every claim must have a stable, unique identifier.",
            raw_input=item,
        )

    claim_id = item.claim_id.strip()

    # R2: text must be non-empty
    if not item.text or not item.text.strip():
        return ParseRejection(
            claim_id=claim_id,
            reason=_REASON_EMPTY_TEXT,
            detail=(
                f"Claim '{claim_id}' has empty or whitespace-only text. "
                "A claim with no text cannot be evaluated for compliance."
            ),
            raw_input=item,
        )

    # R3: source_ref must have usable source_id and source_type
    sr = item.source_ref
    if (
        not sr.source_type
        or not sr.source_type.strip()
        or not sr.source_id
        or not sr.source_id.strip()
    ):
        return ParseRejection(
            claim_id=claim_id,
            reason=_REASON_BAD_SOURCE_REF,
            detail=(
                f"Claim '{claim_id}' has an unusable source_ref: "
                f"source_type={sr.source_type!r}, source_id={sr.source_id!r}. "
                "Both must be non-empty for the claim to be traceable."
            ),
            raw_input=item,
        )

    # R4: section must start with "S."
    if not item.section.startswith("S."):
        return ParseRejection(
            claim_id=claim_id,
            reason=_REASON_WRONG_SECTION,
            detail=(
                f"Claim '{claim_id}' belongs to section {item.section!r}, "
                "which does not start with 'S.'. The S.6 parser only handles "
                "substance (S.*) section claims."
            ),
            raw_input=item,
        )

    return None  # all checks passed
