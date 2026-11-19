"""
Shared Pydantic v2 data contracts for the Container Closure Agent S6
project.

Design notes (see Architecture Proposal v4 for full rationale):

* All timestamps are timezone-aware and normalised to UTC. Naive
  datetimes are rejected at validation time. Serialisation produces
  an explicit "...Z" suffix, matching the SQLite column default
  format (strftime('%Y-%m-%dT%H:%M:%fZ','now'), which yields
  millisecond precision).
* FindingRecord carries `event_id` (not the other way around) --
  every finding is traceable to the single audit event that produced
  it. See shared/schema.py for the matching composite foreign key.
* HumanGateDecision enforces, at the model level, that
  `overridden_verdict` is set if and only if `decision == OVERRIDDEN`.
* A contradiction finding (finding_type == CONTRADICTION) may only
  carry verdict == NON_COMPLIANT if it also carries a `citation` --
  i.e. a specific regulatory requirement the discrepancy breaches.
  Otherwise a contradiction defaults to NEEDS_REVIEW.
* Mutable defaults (lists, dicts) all use Field(default_factory=...).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator

from .enums import (
    AgentName,
    ComparisonFieldType,
    DecisionOutcome,
    EventStatus,
    FindingType,
    Severity,
    Verdict,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc_timestamp(value: str) -> datetime:
    """Parse a stored "...Z" timestamp string back into a
    timezone-aware UTC datetime. Used by tests and, in a later
    phase, by shared/query.py when reading rows back from SQLite."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


class _UTCTimestampedModel(BaseModel):
    """Mixin providing a single, consistently validated and
    serialised `timestamp` field. Models needing a timestamp inherit
    from this instead of redeclaring the field and its rules."""

    timestamp: datetime = Field(default_factory=utc_now)

    @field_validator("timestamp")
    @classmethod
    def _require_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError(
                "timestamp must be timezone-aware (naive datetimes are "
                "rejected); construct it with datetime.now(timezone.utc) "
                "or an equivalent aware value"
            )
        return value.astimezone(timezone.utc)

    @field_serializer("timestamp")
    def _serialize_timestamp(self, value: datetime) -> str:
        # strftime("%f") always yields exactly 6 digits of
        # microseconds; dropping the last 3 gives millisecond
        # precision, matching SQLite's strftime('%f') format used in
        # the schema's server-side column defaults.
        formatted = value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")
        return formatted[:-3] + "Z"


# ---------------------------------------------------------------------------
# Traceability
# ---------------------------------------------------------------------------


class SourceReference(BaseModel):
    """Traceable link back to the origin of a claim, requirement or
    condition. Every FindingRecord's evidence must be traceable via
    one or more of these -- the S.6 agent must never produce a
    finding whose claim or citation cannot be traced to a
    SourceReference."""

    source_type: str  # "m3_extraction" | "m2_rkb" | "m4b_stability" | "sponsor_dossier"
    source_id: str
    section: str
    document: str | None = None
    page: int | None = None
    field_path: str | None = None


# ---------------------------------------------------------------------------
# Input contracts (what the S.6 agent receives from other members)
# ---------------------------------------------------------------------------


class S6Claim(BaseModel):
    """A single packaging/closure claim extracted by M3. The exact
    shape of M3's real output is not yet confirmed (see Architecture
    Proposal v4, Section 10, item 1) -- this is our own contract,
    which a future m3_adapter.py will populate from whatever M3
    actually returns."""

    claim_id: str
    section: str = "S.6"
    text: str
    source_ref: SourceReference
    batch_numbers: list[str] = Field(default_factory=list)
    packaging_components: list[str] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    quantitative_values: dict[str, str] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class S7StabilityCondition(BaseModel):
    """Stability conditions from M4b, used for S.6/S.7 cross-
    reference. The exact shape of M4b's real output is not yet
    confirmed (Architecture Proposal v4, Section 10, item 3)."""

    condition_id: str
    section: str = "S.7"
    storage_condition: str
    container_reference: str | None = None
    batch_number: str | None = None
    packaging_reference: str | None = None
    dates: list[str] = Field(default_factory=list)
    source_ref: SourceReference
    detail: dict[str, Any] = Field(default_factory=dict)


class RKBRequirement(BaseModel):
    """An ICH guideline requirement retrieved from M2's Regulatory
    Knowledge Base. The exact shape of M2's real query interface is
    not yet confirmed (Architecture Proposal v4, Section 10, item 2)."""

    requirement_id: str
    guideline: str
    section: str
    text: str
    citation: str
    source_ref: SourceReference


# ---------------------------------------------------------------------------
# Audit contracts (aligned 1:1 with shared/schema.py)
# ---------------------------------------------------------------------------


class AuditEvent(_UTCTimestampedModel):
    """An agent action recorded in the `events` table.

    Lifecycle (see Architecture Proposal v4, Section 6):
    * A `started` event has parent_event_id = NULL if it is a
      top-level run, or the top-level run's event id if it is a
      sub-operation initiated within that run.
    * Its matching terminal event (`completed` or `failed`) sets
      parent_event_id to the id of *this* `started` event.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    agent_name: AgentName
    action: str
    status: EventStatus
    parent_event_id: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class ContradictionDetail(BaseModel):
    """Structured detail for a contradiction finding. Serialised
    into FindingRecord.detail["contradiction"] -- there is no
    separate contradictions table (Architecture Proposal v4,
    Section 3)."""

    field_type: ComparisonFieldType
    value_a: str
    section_a: str
    claim_id_a: str | None = None
    agent_name_a: AgentName | None = None
    source_ref_a: SourceReference | None = None
    value_b: str
    section_b: str
    claim_id_b: str | None = None
    agent_name_b: AgentName | None = None
    source_ref_b: SourceReference | None = None
    explanation: str


class FindingRecord(_UTCTimestampedModel):
    """Structured finding -- aligned 1:1 with the `findings` table.

    Validation rule (Architecture Proposal v4, Section 5): a
    contradiction finding (finding_type == CONTRADICTION) may only
    be marked NON_COMPLIANT if `citation` identifies the specific
    regulatory requirement it breaches. Without a citation, a
    contradiction must be NEEDS_REVIEW (the default) or
    INSUFFICIENT_DATA -- the consistency agent detects discrepancies,
    it does not independently adjudicate regulatory breaches.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    event_id: str
    session_id: str
    agent_name: AgentName
    finding_type: FindingType = FindingType.COMPLIANCE
    section: str
    claim_text: str | None = None
    claim_id: str | None = None
    requirement: str | None = None
    requirement_id: str | None = None
    verdict: Verdict
    severity: Severity
    citation: str | None = None
    rationale: str
    linked_sections: list[str] = Field(default_factory=list)
    source_refs: list[SourceReference] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_non_compliant_contradiction_has_citation(self) -> "FindingRecord":
        if (
            self.finding_type == FindingType.CONTRADICTION
            and self.verdict == Verdict.NON_COMPLIANT
            and not self.citation
        ):
            raise ValueError(
                "a contradiction finding marked NON_COMPLIANT must carry a "
                "citation identifying the specific regulatory requirement "
                "it breaches; without one it must be NEEDS_REVIEW or "
                "INSUFFICIENT_DATA"
            )
        return self


class HumanGateDecision(_UTCTimestampedModel):
    """Record of a human assessor's decision at a Human Gate.

    Validation rule (Architecture Proposal v4, Section 4):
    `overridden_verdict` is required when decision == OVERRIDDEN, and
    forbidden for every other DecisionOutcome. The original finding
    row is never modified by a decision -- see shared/schema.py's
    append-only triggers and shared/query.py's (Phase 2)
    get_effective_verdict() for how an override is resolved without
    mutating the finding.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    finding_id: str
    session_id: str
    gate_name: str
    assessor: str
    decision: DecisionOutcome
    note: str
    overridden_verdict: Verdict | None = None

    @model_validator(mode="after")
    def _validate_overridden_verdict_pairing(self) -> "HumanGateDecision":
        if self.decision == DecisionOutcome.OVERRIDDEN:
            if self.overridden_verdict is None:
                raise ValueError(
                    "overridden_verdict is required when decision is OVERRIDDEN"
                )
        else:
            if self.overridden_verdict is not None:
                raise ValueError(
                    f"overridden_verdict must be None when decision is "
                    f"{self.decision.value} (only OVERRIDDEN may set it)"
                )
        return self
