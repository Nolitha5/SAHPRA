"""
Pydantic v2 model validation tests (Architecture Proposal v4,
Sections 3, 4, 5, 7).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from shared.enums import (
    AgentName,
    ComparisonFieldType,
    DecisionOutcome,
    EventStatus,
    FindingType,
    Severity,
    Verdict,
)
from shared.models import (
    AuditEvent,
    ContradictionDetail,
    FindingRecord,
    HumanGateDecision,
    parse_utc_timestamp,
)


# ---------------------------------------------------------------------------
# Timestamp handling
# ---------------------------------------------------------------------------


def test_timestamp_defaults_to_timezone_aware_utc():
    ev = AuditEvent(
        session_id="s1", agent_name=AgentName.S6_CONTAINER_CLOSURE,
        action="run", status=EventStatus.STARTED,
    )
    assert ev.timestamp.tzinfo is not None
    assert ev.timestamp.utcoffset() == timedelta(0)


def test_timestamp_serialization_has_z_suffix_and_millisecond_precision():
    ev = AuditEvent(
        session_id="s1", agent_name=AgentName.S6_CONTAINER_CLOSURE,
        action="run", status=EventStatus.STARTED,
        timestamp=datetime(2026, 11, 10, 9, 30, 45, 123456, tzinfo=timezone.utc),
    )
    dumped = ev.model_dump()
    assert dumped["timestamp"] == "2026-11-10T09:30:45.123Z"


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValidationError):
        AuditEvent(
            session_id="s1", agent_name=AgentName.S6_CONTAINER_CLOSURE,
            action="run", status=EventStatus.STARTED,
            timestamp=datetime(2026, 11, 10, 9, 30, 45),  # naive
        )


def test_non_utc_timezone_is_normalized_to_utc():
    sast = timezone(timedelta(hours=2))  # Africa/Johannesburg, fixed offset
    local_dt = datetime(2026, 11, 10, 11, 30, 0, tzinfo=sast)
    ev = AuditEvent(
        session_id="s1", agent_name=AgentName.S6_CONTAINER_CLOSURE,
        action="run", status=EventStatus.STARTED,
        timestamp=local_dt,
    )
    assert ev.timestamp == local_dt.astimezone(timezone.utc)
    assert ev.model_dump()["timestamp"] == "2026-11-10T09:30:00.000Z"


def test_parse_utc_timestamp_round_trips():
    ev = AuditEvent(
        session_id="s1", agent_name=AgentName.S6_CONTAINER_CLOSURE,
        action="run", status=EventStatus.STARTED,
    )
    serialized = ev.model_dump()["timestamp"]
    parsed = parse_utc_timestamp(serialized)
    assert parsed.tzinfo is not None
    # millisecond precision means sub-millisecond difference is expected
    assert abs((parsed - ev.timestamp).total_seconds()) < 0.001


# ---------------------------------------------------------------------------
# Mutable defaults
# ---------------------------------------------------------------------------


def test_mutable_defaults_are_independent_across_instances():
    f1 = FindingRecord(
        event_id="e1", session_id="s1", agent_name=AgentName.S6_CONTAINER_CLOSURE,
        section="S.6", verdict=Verdict.COMPLIANT, severity=Severity.INFO, rationale="r",
    )
    f2 = FindingRecord(
        event_id="e2", session_id="s1", agent_name=AgentName.S6_CONTAINER_CLOSURE,
        section="S.6", verdict=Verdict.COMPLIANT, severity=Severity.INFO, rationale="r",
    )
    f1.linked_sections.append("S.7")
    assert f2.linked_sections == []
    f1.detail["x"] = 1
    assert f2.detail == {}


# ---------------------------------------------------------------------------
# HumanGateDecision validation (Section 4)
# ---------------------------------------------------------------------------


def test_overridden_requires_overridden_verdict():
    with pytest.raises(ValidationError):
        HumanGateDecision(
            finding_id="f1", session_id="s1", gate_name="g", assessor="a",
            decision=DecisionOutcome.OVERRIDDEN, note="n",
        )


def test_overridden_with_verdict_succeeds():
    decision = HumanGateDecision(
        finding_id="f1", session_id="s1", gate_name="g", assessor="a",
        decision=DecisionOutcome.OVERRIDDEN, note="n",
        overridden_verdict=Verdict.COMPLIANT,
    )
    assert decision.overridden_verdict == Verdict.COMPLIANT


@pytest.mark.parametrize(
    "outcome",
    [
        DecisionOutcome.APPROVED,
        DecisionOutcome.REJECTED,
        DecisionOutcome.REFERRED,
        DecisionOutcome.ADDITIONAL_INFO,
        DecisionOutcome.DEFERRED,
    ],
)
def test_non_overridden_outcomes_reject_overridden_verdict(outcome):
    with pytest.raises(ValidationError):
        HumanGateDecision(
            finding_id="f1", session_id="s1", gate_name="g", assessor="a",
            decision=outcome, note="n", overridden_verdict=Verdict.COMPLIANT,
        )


@pytest.mark.parametrize(
    "outcome",
    [
        DecisionOutcome.APPROVED,
        DecisionOutcome.REJECTED,
        DecisionOutcome.REFERRED,
        DecisionOutcome.ADDITIONAL_INFO,
        DecisionOutcome.DEFERRED,
    ],
)
def test_non_overridden_outcomes_succeed_without_overridden_verdict(outcome):
    decision = HumanGateDecision(
        finding_id="f1", session_id="s1", gate_name="g", assessor="a",
        decision=outcome, note="n",
    )
    assert decision.overridden_verdict is None


def test_human_gate_decision_requires_note():
    with pytest.raises(ValidationError):
        HumanGateDecision(
            finding_id="f1", session_id="s1", gate_name="g", assessor="a",
            decision=DecisionOutcome.APPROVED, note=None,
        )


# ---------------------------------------------------------------------------
# Contradiction verdict validation (Section 5)
# ---------------------------------------------------------------------------


def test_contradiction_non_compliant_without_citation_is_rejected():
    with pytest.raises(ValidationError):
        FindingRecord(
            event_id="e1", session_id="s1", agent_name=AgentName.CROSS_SECTION,
            finding_type=FindingType.CONTRADICTION, section="S.6",
            verdict=Verdict.NON_COMPLIANT, severity=Severity.MAJOR, rationale="r",
        )


def test_contradiction_non_compliant_with_citation_succeeds():
    finding = FindingRecord(
        event_id="e1", session_id="s1", agent_name=AgentName.CROSS_SECTION,
        finding_type=FindingType.CONTRADICTION, section="S.6",
        verdict=Verdict.NON_COMPLIANT, severity=Severity.MAJOR, rationale="r",
        citation="ICH Q6A 1.2",
    )
    assert finding.citation == "ICH Q6A 1.2"


def test_contradiction_needs_review_without_citation_succeeds():
    finding = FindingRecord(
        event_id="e1", session_id="s1", agent_name=AgentName.CROSS_SECTION,
        finding_type=FindingType.CONTRADICTION, section="S.6",
        verdict=Verdict.NEEDS_REVIEW, severity=Severity.MINOR, rationale="r",
    )
    assert finding.citation is None


def test_compliance_finding_non_compliant_without_citation_is_allowed():
    """The citation requirement is specific to CONTRADICTION findings,
    not to every NON_COMPLIANT verdict -- an ordinary S.6 compliance
    finding may be NON_COMPLIANT with or without a citation (its own
    evaluator logic, not a model-level rule, governs that)."""
    finding = FindingRecord(
        event_id="e1", session_id="s1", agent_name=AgentName.S6_CONTAINER_CLOSURE,
        finding_type=FindingType.COMPLIANCE, section="S.6",
        verdict=Verdict.NON_COMPLIANT, severity=Severity.MAJOR, rationale="r",
    )
    assert finding.finding_type == FindingType.COMPLIANCE


def test_finding_type_defaults_to_compliance():
    finding = FindingRecord(
        event_id="e1", session_id="s1", agent_name=AgentName.S6_CONTAINER_CLOSURE,
        section="S.6", verdict=Verdict.COMPLIANT, severity=Severity.INFO, rationale="r",
    )
    assert finding.finding_type == FindingType.COMPLIANCE


# ---------------------------------------------------------------------------
# ContradictionDetail enum validation (Section 7)
# ---------------------------------------------------------------------------


def test_contradiction_detail_rejects_invalid_field_type():
    with pytest.raises(ValidationError):
        ContradictionDetail(
            field_type="not_a_real_type", value_a="1", section_a="S.6",
            value_b="2", section_b="S.7", explanation="x",
        )


@pytest.mark.parametrize(
    "field_type",
    [
        ComparisonFieldType.BATCH_NUMBER,
        ComparisonFieldType.DATE,
        ComparisonFieldType.QUANTITY,
        ComparisonFieldType.PACKAGING_REFERENCE,
    ],
)
def test_contradiction_detail_accepts_all_defined_field_types(field_type):
    detail = ContradictionDetail(
        field_type=field_type, value_a="A", section_a="S.6",
        value_b="B", section_b="S.7", explanation="x",
    )
    assert detail.field_type == field_type


def test_contradiction_detail_preserves_both_sides_fully():
    detail = ContradictionDetail(
        field_type=ComparisonFieldType.BATCH_NUMBER,
        value_a="BATCH-001", section_a="S.6", claim_id_a="c1",
        agent_name_a=AgentName.S6_CONTAINER_CLOSURE,
        value_b="BATCH-002", section_b="S.7", claim_id_b="c2",
        agent_name_b=AgentName.S7_STABILITY,
        explanation="batch numbers disagree",
    )
    dumped = detail.model_dump()
    assert dumped["value_a"] == "BATCH-001" and dumped["value_b"] == "BATCH-002"
    assert dumped["section_a"] == "S.6" and dumped["section_b"] == "S.7"
    assert dumped["claim_id_a"] == "c1" and dumped["claim_id_b"] == "c2"
