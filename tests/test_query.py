"""
Tests for the shared audit query layer (shared/query.py), Phase 3.
"""
from __future__ import annotations

import pytest
from sqlalchemy import insert, text

from shared.audit import execution_scope, write_decision, write_event, write_finding
from shared.database import create_memory_engine, create_readonly_engine, create_write_engine
from shared.enums import AgentName, DecisionOutcome, EventStatus, FindingType, Severity, Verdict
from shared.exceptions import AuditError, AuditQueryError, AuditWriteError
from shared.models import AuditEvent, FindingRecord, HumanGateDecision
from shared.query import (
    AuditNotFoundError,
    EffectiveVerdict,
    UnfinishedEvent,
    get_effective_verdict,
    get_event,
    get_finding,
    get_finding_decisions,
    get_session_events,
    get_session_findings,
    get_unfinished_events,
)
from shared.schema import decisions, events, findings, init_database

S6 = AgentName.S6_CONTAINER_CLOSURE


def _event(session_id="s1", **kw) -> AuditEvent:
    base = dict(session_id=session_id, agent_name=S6, action="run", status=EventStatus.STARTED)
    base.update(kw)
    return AuditEvent(**base)


def _finding(event_id, session_id="s1", **kw) -> FindingRecord:
    base = dict(event_id=event_id, session_id=session_id, agent_name=S6, section="S.6",
                verdict=Verdict.COMPLIANT, severity=Severity.INFO, rationale="r")
    base.update(kw)
    return FindingRecord(**base)


def _decision(finding_id, session_id="s1", **kw) -> HumanGateDecision:
    base = dict(finding_id=finding_id, session_id=session_id, gate_name="g",
                assessor="a", decision=DecisionOutcome.APPROVED, note="n")
    base.update(kw)
    return HumanGateDecision(**base)


@pytest.fixture()
def populated(memory_engine):
    """One session with a nested lifecycle, two findings, decisions on
    one of them; plus a second session with its own records."""
    e = memory_engine
    with execution_scope(e, session_id="s1", agent_name=S6, action="run_s6") as run:
        with execution_scope(e, session_id="s1", agent_name=S6, action="evaluate",
                             parent_event_id=run.id) as ev:
            f1 = _finding(ev.id, verdict=Verdict.NON_COMPLIANT, severity=Severity.MAJOR,
                          linked_sections=["S.7"], detail={"k": 1})
            f2 = _finding(ev.id, agent_name=AgentName.CROSS_SECTION,
                          finding_type=FindingType.CONTRADICTION, verdict=Verdict.NEEDS_REVIEW)
            write_finding(e, f1); write_finding(e, f2)
    d1 = _decision(f1.id, decision=DecisionOutcome.REFERRED, note="escalate")
    d2 = _decision(f1.id, decision=DecisionOutcome.OVERRIDDEN,
                   overridden_verdict=Verdict.COMPLIANT, note="override")
    write_decision(e, d1); write_decision(e, d2)
    # second, unrelated session
    other = _event(session_id="s2"); write_event(e, other)
    of = _finding(other.id, session_id="s2"); write_finding(e, of)
    return dict(engine=e, run=run, ev=ev, f1=f1, f2=f2, d1=d1, d2=d2, other=other, of=of)


# ---------------------------------------------------------------------------
# Event retrieval and timeline
# ---------------------------------------------------------------------------


def test_get_event_returns_validated_model(populated):
    got = get_event(populated["engine"], populated["run"].id, session_id="s1")
    assert isinstance(got, AuditEvent)
    assert got.id == populated["run"].id
    assert got.status == EventStatus.STARTED and got.agent_name == S6
    assert got.timestamp.tzinfo is not None
    assert got.detail == {}


def test_get_session_events_is_full_ordered_timeline(populated):
    timeline = get_session_events(populated["engine"], "s1")
    assert [(e.action, e.status.value) for e in timeline] == [
        ("run_s6", "started"), ("evaluate", "started"),
        ("evaluate", "completed"), ("run_s6", "completed"),
    ]
    assert timeline[2].parent_event_id == populated["ev"].id
    assert timeline[3].parent_event_id == populated["run"].id


def test_get_session_events_unknown_session_is_empty(populated):
    assert get_session_events(populated["engine"], "never-existed") == []


def test_timeline_ordering_is_deterministic_within_same_millisecond(memory_engine):
    """Rows inserted with an identical timestamp must come back in
    insertion order every time (rowid tie-break)."""
    ts = "2026-11-11T09:00:00.000Z"
    with memory_engine.begin() as conn:
        for i in range(5):
            conn.execute(insert(events).values(
                id=f"e{i}", session_id="s", timestamp=ts, agent_name=S6.value,
                action=f"a{i}", status="started"))
    for _ in range(3):
        assert [e.id for e in get_session_events(memory_engine, "s")] == [f"e{i}" for i in range(5)]


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


def test_get_finding_round_trips_all_fields(populated):
    got = get_finding(populated["engine"], populated["f1"].id, session_id="s1")
    assert isinstance(got, FindingRecord)
    assert got.event_id == populated["ev"].id
    assert got.verdict == Verdict.NON_COMPLIANT and got.severity == Severity.MAJOR
    assert got.linked_sections == ["S.7"] and got.detail == {"k": 1}
    assert got.finding_type == FindingType.COMPLIANCE


def test_get_session_findings_and_type_filter(populated):
    e = populated["engine"]
    all_f = get_session_findings(e, "s1")
    assert [f.id for f in all_f] == [populated["f1"].id, populated["f2"].id]
    contradictions = get_session_findings(e, "s1", finding_type=FindingType.CONTRADICTION)
    assert [f.id for f in contradictions] == [populated["f2"].id]
    assert contradictions[0].agent_name == AgentName.CROSS_SECTION


# ---------------------------------------------------------------------------
# Decision history and effective verdict
# ---------------------------------------------------------------------------


def test_get_finding_decisions_returns_complete_ordered_history(populated):
    hist = get_finding_decisions(populated["engine"], populated["f1"].id, session_id="s1")
    assert [d.id for d in hist] == [populated["d1"].id, populated["d2"].id]
    assert [d.decision for d in hist] == [DecisionOutcome.REFERRED, DecisionOutcome.OVERRIDDEN]
    assert hist[1].overridden_verdict == Verdict.COMPLIANT
    assert all(isinstance(d, HumanGateDecision) for d in hist)


def test_get_finding_decisions_empty_when_finding_has_none(populated):
    assert get_finding_decisions(populated["engine"], populated["f2"].id, session_id="s1") == []


def test_effective_verdict_without_decisions_is_original(populated):
    ev = get_effective_verdict(populated["engine"], populated["f2"].id, session_id="s1")
    assert isinstance(ev, EffectiveVerdict)
    assert ev.original_verdict == ev.effective_verdict == Verdict.NEEDS_REVIEW
    assert ev.overridden is False and ev.overriding_decision_id is None and ev.decision_count == 0


def test_effective_verdict_applies_latest_override_and_keeps_original(populated):
    e = populated["engine"]
    ev = get_effective_verdict(e, populated["f1"].id, session_id="s1")
    assert ev.original_verdict == Verdict.NON_COMPLIANT
    assert ev.effective_verdict == Verdict.COMPLIANT
    assert ev.overridden is True and ev.overriding_decision_id == populated["d2"].id
    assert ev.decision_count == 2
    # the stored finding is untouched
    assert get_finding(e, populated["f1"].id, session_id="s1").verdict == Verdict.NON_COMPLIANT


def test_multiple_overrides_latest_wins_and_history_is_preserved(populated):
    e, f1 = populated["engine"], populated["f1"]
    d3 = _decision(f1.id, decision=DecisionOutcome.OVERRIDDEN,
                   overridden_verdict=Verdict.NEEDS_REVIEW, note="second override")
    write_decision(e, d3)
    ev = get_effective_verdict(e, f1.id, session_id="s1")
    assert ev.effective_verdict == Verdict.NEEDS_REVIEW
    assert ev.overriding_decision_id == d3.id and ev.decision_count == 3
    hist = get_finding_decisions(e, f1.id, session_id="s1")
    assert [d.overridden_verdict for d in hist] == [None, Verdict.COMPLIANT, Verdict.NEEDS_REVIEW]


def test_non_override_decision_after_override_reverts_to_original(populated):
    """v4 Section 4.2 semantics: only the MOST RECENT decision counts.
    A later non-OVERRIDDEN decision means the original verdict is
    effective again."""
    e, f1 = populated["engine"], populated["f1"]
    write_decision(e, _decision(f1.id, decision=DecisionOutcome.APPROVED, note="later approval"))
    ev = get_effective_verdict(e, f1.id, session_id="s1")
    assert ev.effective_verdict == Verdict.NON_COMPLIANT
    assert ev.overridden is False and ev.decision_count == 3


def test_effective_verdict_rejects_corrupt_override_row(memory_engine):
    """An OVERRIDDEN row with no overridden_verdict cannot be created
    through the audit layer; if it exists anyway, the query layer must
    refuse to guess."""
    ev = _event(); write_event(memory_engine, ev)
    f = _finding(ev.id); write_finding(memory_engine, f)
    with memory_engine.begin() as conn:
        conn.execute(insert(decisions).values(
            id="corrupt", finding_id=f.id, session_id="s1", timestamp="2026-01-01T00:00:00.000Z",
            gate_name="g", assessor="a", decision="OVERRIDDEN", note="n", overridden_verdict=None))
    with pytest.raises(AuditQueryError, match="violates the HumanGateDecision contract"):
        get_effective_verdict(memory_engine, f.id, session_id="s1")


# ---------------------------------------------------------------------------
# Unfinished events
# ---------------------------------------------------------------------------


def test_unfinished_events_none_when_all_scopes_closed(populated):
    assert get_unfinished_events(populated["engine"], "s1") == []


def test_unfinished_started_event_has_unknown_outcome_not_failed(memory_engine):
    orphan = _event(action="run_s6")
    write_event(memory_engine, orphan)  # no terminal partner ever written
    result = get_unfinished_events(memory_engine, "s1")
    assert len(result) == 1
    assert isinstance(result[0], UnfinishedEvent)
    assert result[0].event.id == orphan.id
    assert result[0].outcome == "unknown"
    assert result[0].event.status == EventStatus.STARTED
    # the model cannot even express "failed"
    with pytest.raises(Exception):
        UnfinishedEvent(event=orphan, outcome="failed")


def test_unfinished_detection_in_nested_scopes(memory_engine):
    e = memory_engine
    run = _event(action="run"); write_event(e, run)
    sub_done = _event(action="sub_done", parent_event_id=run.id); write_event(e, sub_done)
    write_event(e, _event(action="sub_done", status=EventStatus.COMPLETED, parent_event_id=sub_done.id))
    sub_failed = _event(action="sub_failed", parent_event_id=run.id); write_event(e, sub_failed)
    write_event(e, _event(action="sub_failed", status=EventStatus.FAILED, parent_event_id=sub_failed.id))
    sub_open = _event(action="sub_open", parent_event_id=run.id); write_event(e, sub_open)
    # `run` itself and `sub_open` never got a terminal event
    unfinished = get_unfinished_events(e, "s1")
    assert {u.event.action for u in unfinished} == {"run", "sub_open"}
    assert all(u.outcome == "unknown" for u in unfinished)


def test_terminal_event_in_other_session_does_not_close_a_started_event(memory_engine):
    """A terminal row cannot belong to a different session (composite
    FK), but the query must not rely on that alone: filter by session."""
    started = _event(session_id="A"); write_event(memory_engine, started)
    # no way to create a cross-session terminal via the audit layer, so
    # the started event must show as unfinished in A and absent in B
    assert [u.event.id for u in get_unfinished_events(memory_engine, "A")] == [started.id]
    assert get_unfinished_events(memory_engine, "B") == []


# ---------------------------------------------------------------------------
# Cross-session isolation
# ---------------------------------------------------------------------------


def test_record_in_other_session_is_not_found(populated):
    e = populated["engine"]
    with pytest.raises(AuditNotFoundError):
        get_event(e, populated["run"].id, session_id="s2")
    with pytest.raises(AuditNotFoundError):
        get_finding(e, populated["f1"].id, session_id="s2")
    with pytest.raises(AuditNotFoundError):
        get_finding_decisions(e, populated["f1"].id, session_id="s2")
    with pytest.raises(AuditNotFoundError):
        get_effective_verdict(e, populated["f1"].id, session_id="s2")


def test_session_lists_do_not_leak_other_sessions(populated):
    e = populated["engine"]
    assert {ev.session_id for ev in get_session_events(e, "s1")} == {"s1"}
    assert {ev.session_id for ev in get_session_events(e, "s2")} == {"s2"}
    assert [f.id for f in get_session_findings(e, "s2")] == [populated["of"].id]
    assert len(get_session_events(e, "s2")) == 1


# ---------------------------------------------------------------------------
# Read-only enforcement
# ---------------------------------------------------------------------------


def test_all_queries_work_through_readonly_engine_and_it_cannot_write(seeded_file_db):
    db_path, write_engine = seeded_file_db
    ro = create_readonly_engine(db_path)
    assert get_event(ro, "seed-e1", session_id="sess-seed").action == "run_s6"
    assert len(get_session_events(ro, "sess-seed")) == 1
    assert get_finding(ro, "seed-f1", session_id="sess-seed").verdict == Verdict.COMPLIANT
    assert len(get_session_findings(ro, "sess-seed")) == 1
    assert len(get_finding_decisions(ro, "seed-f1", session_id="sess-seed")) == 1
    assert get_effective_verdict(ro, "seed-f1", session_id="sess-seed").overridden is False
    assert [u.event.id for u in get_unfinished_events(ro, "sess-seed")] == ["seed-e1"]
    # the same engine refuses writes
    with pytest.raises(AuditWriteError, match="readonly"):
        write_event(ro, _event(session_id="sess-seed"))
    # and sees a write made by the write engine afterwards (WAL)
    write_event(write_engine, _event(session_id="sess-seed", action="later"))
    assert len(get_session_events(ro, "sess-seed")) == 2


def test_query_module_exposes_no_write_functions():
    import shared.query as q

    names = {n for n in dir(q) if not n.startswith("_") and callable(getattr(q, n))}
    assert {n for n in names if n.startswith("get_")} == {
        "get_event", "get_session_events", "get_finding", "get_session_findings",
        "get_finding_decisions", "get_effective_verdict", "get_unfinished_events",
    }
    assert not any(n.startswith(("write_", "update_", "delete_", "set_")) for n in names)


# ---------------------------------------------------------------------------
# Missing records and database errors
# ---------------------------------------------------------------------------


def test_missing_records_raise_not_found_with_clear_messages(memory_engine):
    with pytest.raises(AuditNotFoundError, match="event 'nope' not found in session 's1'"):
        get_event(memory_engine, "nope", session_id="s1")
    with pytest.raises(AuditNotFoundError, match="finding 'nope' not found"):
        get_finding(memory_engine, "nope", session_id="s1")
    with pytest.raises(AuditNotFoundError):
        get_finding_decisions(memory_engine, "nope", session_id="s1")
    with pytest.raises(AuditNotFoundError):
        get_effective_verdict(memory_engine, "nope", session_id="s1")


def test_not_found_is_part_of_established_hierarchy():
    assert issubclass(AuditNotFoundError, AuditQueryError)
    assert issubclass(AuditQueryError, AuditError)


def test_database_errors_are_wrapped(tmp_path):
    """An engine over a database with no schema produces a real
    SQLite error; it must surface as AuditQueryError, not a raw
    SQLAlchemy exception."""
    engine = create_write_engine(str(tmp_path / "empty.db"))  # init_database NOT called
    with pytest.raises(AuditQueryError, match="no such table"):
        get_session_events(engine, "s1")
    with pytest.raises(AuditQueryError, match="no such table"):
        get_effective_verdict(engine, "f", session_id="s1")


def test_corrupt_stored_row_is_reported_not_skipped(memory_engine):
    ev = _event(); write_event(memory_engine, ev)
    with memory_engine.begin() as conn:
        conn.execute(insert(findings).values(
            id="bad", event_id=ev.id, session_id="s1", timestamp="t", agent_name="not-an-agent",
            section="S.6", verdict="MAYBE", severity="INFO", rationale="r"))
    with pytest.raises(AuditQueryError, match="could not be validated"):
        get_session_findings(memory_engine, "s1")
