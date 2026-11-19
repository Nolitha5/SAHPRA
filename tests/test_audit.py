"""
Tests for the shared audit write layer (shared/audit.py), Phase 2.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select, text

from shared.audit import execution_scope, write_decision, write_event, write_finding
from shared.database import create_readonly_engine
from shared.enums import (
    AgentName,
    ComparisonFieldType,
    DecisionOutcome,
    EventStatus,
    FindingType,
    Severity,
    Verdict,
)
from shared.exceptions import AuditWriteError
from shared.models import (
    AuditEvent,
    ContradictionDetail,
    FindingRecord,
    HumanGateDecision,
    SourceReference,
    parse_utc_timestamp,
)
from shared.schema import decisions, events, findings

S6 = AgentName.S6_CONTAINER_CLOSURE


def _event(session_id="s1", **kw) -> AuditEvent:
    base = dict(session_id=session_id, agent_name=S6, action="run", status=EventStatus.STARTED)
    base.update(kw)
    return AuditEvent(**base)


def _finding(event_id, session_id="s1", **kw) -> FindingRecord:
    base = dict(
        event_id=event_id, session_id=session_id, agent_name=S6, section="S.6",
        verdict=Verdict.COMPLIANT, severity=Severity.INFO, rationale="r",
    )
    base.update(kw)
    return FindingRecord(**base)


def _decision(finding_id, session_id="s1", **kw) -> HumanGateDecision:
    base = dict(
        finding_id=finding_id, session_id=session_id, gate_name="gate-1",
        assessor="assessor-1", decision=DecisionOutcome.APPROVED, note="n",
    )
    base.update(kw)
    return HumanGateDecision(**base)


def _count(engine, table) -> int:
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar_one()


# ---------------------------------------------------------------------------
# Successful writes
# ---------------------------------------------------------------------------


def test_write_event_persists_all_fields(memory_engine):
    ev = _event(detail={"k": "v"})
    returned_id = write_event(memory_engine, ev)
    assert returned_id == ev.id
    with memory_engine.connect() as conn:
        row = conn.execute(select(events).where(events.c.id == ev.id)).one()
    assert row.session_id == "s1"
    assert row.agent_name == "s6_container_closure"   # enum stored as value
    assert row.status == "started"
    assert row.parent_event_id is None
    assert json.loads(row.detail) == {"k": "v"}
    assert row.timestamp.endswith("Z") and len(row.timestamp) == len("2026-11-11T08:30:00.000Z")
    assert row.created_at.endswith("Z")


def test_write_finding_persists_all_fields(memory_engine):
    ev = _event()
    write_event(memory_engine, ev)
    src = SourceReference(source_type="m3_extraction", source_id="c1", section="S.6", page=3)
    f = _finding(
        ev.id, claim_text="HDPE bottle", claim_id="c1", citation="ICH Q6A 3.2",
        linked_sections=["S.7"], source_refs=[src], detail={"x": 1},
    )
    assert write_finding(memory_engine, f) == f.id
    with memory_engine.connect() as conn:
        row = conn.execute(select(findings).where(findings.c.id == f.id)).one()
    assert row.event_id == ev.id
    assert row.finding_type == "compliance"
    assert row.verdict == "COMPLIANT" and row.severity == "INFO"
    assert json.loads(row.linked_sections) == ["S.7"]
    assert json.loads(row.source_refs)[0]["source_id"] == "c1"
    assert json.loads(row.detail) == {"x": 1}


def test_write_contradiction_finding_round_trips_detail(memory_engine):
    ev = _event(agent_name=AgentName.CROSS_SECTION)
    write_event(memory_engine, ev)
    cd = ContradictionDetail(
        field_type=ComparisonFieldType.BATCH_NUMBER, value_a="B1", section_a="S.6",
        value_b="B2", section_b="S.7", explanation="mismatch",
    )
    f = _finding(
        ev.id, agent_name=AgentName.CROSS_SECTION, finding_type=FindingType.CONTRADICTION,
        verdict=Verdict.NEEDS_REVIEW, linked_sections=["S.6", "S.7"],
        detail={"contradiction": cd.model_dump(mode="json")},
    )
    write_finding(memory_engine, f)
    with memory_engine.connect() as conn:
        row = conn.execute(select(findings).where(findings.c.id == f.id)).one()
    stored = json.loads(row.detail)["contradiction"]
    assert stored["field_type"] == "batch_number"
    assert stored["value_a"] == "B1" and stored["value_b"] == "B2"
    assert row.finding_type == "contradiction" and row.verdict == "NEEDS_REVIEW"


def test_write_decision_persists_all_fields(memory_engine):
    ev = _event(); write_event(memory_engine, ev)
    f = _finding(ev.id); write_finding(memory_engine, f)
    d = _decision(f.id)
    assert write_decision(memory_engine, d) == d.id
    with memory_engine.connect() as conn:
        row = conn.execute(select(decisions).where(decisions.c.id == d.id)).one()
    assert row.finding_id == f.id
    assert row.assessor == "assessor-1" and row.decision == "APPROVED"
    assert row.note == "n" and row.overridden_verdict is None


def test_timestamp_written_matches_db_default_format(memory_engine):
    ev = _event()
    write_event(memory_engine, ev)
    with memory_engine.connect() as conn:
        row = conn.execute(select(events).where(events.c.id == ev.id)).one()
    # both the model-supplied timestamp and the DB-generated created_at
    # parse to aware UTC datetimes and share the same textual shape
    a, b = parse_utc_timestamp(row.timestamp), parse_utc_timestamp(row.created_at)
    assert a.tzinfo is not None and b.tzinfo is not None
    assert len(row.timestamp) == len(row.created_at)


# ---------------------------------------------------------------------------
# Invalid references
# ---------------------------------------------------------------------------


def test_finding_with_nonexistent_event_is_rejected(memory_engine):
    with pytest.raises(AuditWriteError, match="does not exist"):
        write_finding(memory_engine, _finding("no-such-event"))
    assert _count(memory_engine, findings) == 0


def test_finding_in_wrong_session_is_rejected(memory_engine):
    ev = _event(session_id="sess-A"); write_event(memory_engine, ev)
    with pytest.raises(AuditWriteError, match="cross-session"):
        write_finding(memory_engine, _finding(ev.id, session_id="sess-B"))
    assert _count(memory_engine, findings) == 0


def test_decision_with_nonexistent_finding_is_rejected(memory_engine):
    with pytest.raises(AuditWriteError, match="does not exist"):
        write_decision(memory_engine, _decision("no-such-finding"))
    assert _count(memory_engine, decisions) == 0


def test_decision_in_wrong_session_is_rejected(memory_engine):
    ev = _event(session_id="sess-A"); write_event(memory_engine, ev)
    f = _finding(ev.id, session_id="sess-A"); write_finding(memory_engine, f)
    with pytest.raises(AuditWriteError, match="cross-session"):
        write_decision(memory_engine, _decision(f.id, session_id="sess-B"))
    assert _count(memory_engine, decisions) == 0


def test_event_with_nonexistent_parent_is_rejected(memory_engine):
    with pytest.raises(AuditWriteError, match="parent event .* does not exist"):
        write_event(memory_engine, _event(parent_event_id="ghost"))
    assert _count(memory_engine, events) == 0


def test_event_with_parent_in_wrong_session_is_rejected(memory_engine):
    parent = _event(session_id="sess-A"); write_event(memory_engine, parent)
    with pytest.raises(AuditWriteError, match="cross-session"):
        write_event(memory_engine, _event(session_id="sess-B", parent_event_id=parent.id))
    assert _count(memory_engine, events) == 1


# ---------------------------------------------------------------------------
# Duplicate identifiers
# ---------------------------------------------------------------------------


def test_duplicate_event_id_is_rejected(memory_engine):
    ev = _event(); write_event(memory_engine, ev)
    with pytest.raises(AuditWriteError, match="already exists"):
        write_event(memory_engine, _event(id=ev.id))
    assert _count(memory_engine, events) == 1


def test_duplicate_finding_id_is_rejected(memory_engine):
    ev = _event(); write_event(memory_engine, ev)
    f = _finding(ev.id); write_finding(memory_engine, f)
    with pytest.raises(AuditWriteError, match="already exists"):
        write_finding(memory_engine, _finding(ev.id, id=f.id))
    assert _count(memory_engine, findings) == 1


def test_duplicate_decision_id_is_rejected(memory_engine):
    ev = _event(); write_event(memory_engine, ev)
    f = _finding(ev.id); write_finding(memory_engine, f)
    d = _decision(f.id); write_decision(memory_engine, d)
    with pytest.raises(AuditWriteError, match="already exists"):
        write_decision(memory_engine, _decision(f.id, id=d.id))
    assert _count(memory_engine, decisions) == 1


# ---------------------------------------------------------------------------
# Transaction rollback / database-level failures
# ---------------------------------------------------------------------------


def test_database_constraint_failure_is_wrapped_and_rolled_back(memory_engine, monkeypatch):
    """Bypass the pre-checks to prove the DB constraint still fires,
    is translated to AuditWriteError, and leaves nothing behind."""
    import shared.audit as audit_mod

    monkeypatch.setattr(audit_mod, "_require_same_session", lambda **kw: None)
    with pytest.raises(AuditWriteError, match="failed to write finding"):
        write_finding(memory_engine, _finding("no-such-event"))
    assert _count(memory_engine, findings) == 0


def test_write_through_readonly_engine_is_wrapped(seeded_file_db):
    db_path, _ = seeded_file_db
    ro = create_readonly_engine(db_path)
    with pytest.raises(AuditWriteError, match="readonly"):
        write_event(ro, _event(session_id="sess-seed"))


def test_failed_write_leaves_no_partial_state(memory_engine):
    ev = _event(); write_event(memory_engine, ev)
    before = _count(memory_engine, events)
    with pytest.raises(AuditWriteError):
        write_event(memory_engine, _event(parent_event_id="ghost"))
    assert _count(memory_engine, events) == before
    # the engine is still usable afterwards (no dangling transaction)
    write_event(memory_engine, _event())
    assert _count(memory_engine, events) == before + 1


# ---------------------------------------------------------------------------
# Append-only enforcement through the write layer
# ---------------------------------------------------------------------------


def test_audit_module_exposes_only_insert_style_public_functions():
    import shared.audit as audit_mod

    public = {n for n in dir(audit_mod) if not n.startswith("_") and callable(getattr(audit_mod, n))}
    public -= {"contextmanager", "insert", "select", "AuditEvent", "FindingRecord",
               "HumanGateDecision", "AuditWriteError", "IntegrityError", "OperationalError",
               "AgentName", "EventStatus", "Engine", "Connection", "Iterator", "Any"}
    assert public == {"write_event", "write_finding", "write_decision", "execution_scope"}


def test_rows_written_by_audit_layer_cannot_be_updated_or_deleted(memory_engine):
    from sqlalchemy import delete, update
    from sqlalchemy.exc import IntegrityError

    ev = _event(); write_event(memory_engine, ev)
    with pytest.raises(IntegrityError, match="append-only"):
        with memory_engine.begin() as conn:
            conn.execute(update(events).where(events.c.id == ev.id).values(action="x"))
    with pytest.raises(IntegrityError, match="append-only"):
        with memory_engine.begin() as conn:
            conn.execute(delete(events).where(events.c.id == ev.id))


# ---------------------------------------------------------------------------
# Event lifecycle (execution_scope)
# ---------------------------------------------------------------------------


def test_execution_scope_writes_started_then_completed(memory_engine):
    with execution_scope(memory_engine, session_id="s1", agent_name=S6, action="run_s6") as started:
        assert started.status == EventStatus.STARTED
        with memory_engine.connect() as conn:
            assert conn.execute(select(func.count()).select_from(events)).scalar_one() == 1
    with memory_engine.connect() as conn:
        rows = conn.execute(select(events).order_by(text("rowid"))).all()
    assert [r.status for r in rows] == ["started", "completed"]
    assert rows[1].parent_event_id == started.id
    assert rows[1].action == "run_s6"


def test_execution_scope_writes_failed_on_exception_and_reraises(memory_engine):
    with pytest.raises(ValueError, match="boom"):
        with execution_scope(memory_engine, session_id="s1", agent_name=S6, action="x") as started:
            raise ValueError("boom")
    with memory_engine.connect() as conn:
        rows = conn.execute(select(events).order_by(text("rowid"))).all()
    assert [r.status for r in rows] == ["started", "failed"]
    assert rows[1].parent_event_id == started.id
    assert json.loads(rows[1].detail) == {"error_type": "ValueError", "error_message": "boom"}


def test_execution_scope_nested_subops_and_findings_link_to_started_event(memory_engine):
    with execution_scope(memory_engine, session_id="s1", agent_name=S6, action="run_s6") as run:
        with execution_scope(memory_engine, session_id="s1", agent_name=S6,
                             action="cross_ref_stability", parent_event_id=run.id):
            pass
        with pytest.raises(RuntimeError):
            with execution_scope(memory_engine, session_id="s1", agent_name=S6,
                                 action="retrieve_rkb", parent_event_id=run.id):
                raise RuntimeError("M2 unavailable")
        with execution_scope(memory_engine, session_id="s1", agent_name=S6,
                             action="evaluate_claim", parent_event_id=run.id) as ev_eval:
            write_finding(memory_engine, _finding(ev_eval.id, verdict=Verdict.INSUFFICIENT_DATA,
                                                  rationale="RKB unavailable"))
    with memory_engine.connect() as conn:
        rows = conn.execute(select(events).order_by(text("rowid"))).all()
        f = conn.execute(select(findings)).one()
    statuses = [(r.action, r.status) for r in rows]
    assert statuses == [
        ("run_s6", "started"),
        ("cross_ref_stability", "started"), ("cross_ref_stability", "completed"),
        ("retrieve_rkb", "started"), ("retrieve_rkb", "failed"),
        ("evaluate_claim", "started"), ("evaluate_claim", "completed"),
        ("run_s6", "completed"),
    ]
    # every started event has exactly one terminal partner pointing at it
    started_ids = [r.id for r in rows if r.status == "started"]
    for sid in started_ids:
        partners = [r for r in rows if r.parent_event_id == sid and r.status in ("completed", "failed")]
        assert len(partners) == 1, sid
    # the failed sub-op is still in the timeline, and the finding points
    # at the evaluate_claim started event, not the failed retrieve_rkb one
    assert any(r.status == "failed" for r in rows)
    assert f.event_id == ev_eval.id


def test_execution_scope_original_exception_survives_terminal_write_failure(memory_engine, monkeypatch):
    import shared.audit as audit_mod

    real_write_event = audit_mod.write_event
    calls = {"n": 0}

    def flaky(engine, event):
        calls["n"] += 1
        if event.status == EventStatus.FAILED:
            raise AuditWriteError("db went away")
        return real_write_event(engine, event)

    monkeypatch.setattr(audit_mod, "write_event", flaky)
    with pytest.raises(ValueError, match="original") as exc_info:
        with execution_scope(memory_engine, session_id="s1", agent_name=S6, action="x"):
            raise ValueError("original")
    assert isinstance(exc_info.value.audit_terminal_write_error, AuditWriteError)
    with memory_engine.connect() as conn:
        rows = conn.execute(select(events)).all()
    assert [r.status for r in rows] == ["started"]  # no terminal event -- honestly recorded as such


# ---------------------------------------------------------------------------
# Human decision history and override semantics
# ---------------------------------------------------------------------------


def test_override_persists_without_touching_original_finding(memory_engine):
    ev = _event(); write_event(memory_engine, ev)
    f = _finding(ev.id, verdict=Verdict.NON_COMPLIANT, severity=Severity.MAJOR)
    write_finding(memory_engine, f)
    d = _decision(f.id, decision=DecisionOutcome.OVERRIDDEN, overridden_verdict=Verdict.COMPLIANT,
                  note="assessor disagrees")
    write_decision(memory_engine, d)
    with memory_engine.connect() as conn:
        frow = conn.execute(select(findings).where(findings.c.id == f.id)).one()
        drow = conn.execute(select(decisions).where(decisions.c.id == d.id)).one()
    assert frow.verdict == "NON_COMPLIANT"           # original untouched
    assert drow.decision == "OVERRIDDEN"
    assert drow.overridden_verdict == "COMPLIANT"


def test_multiple_decisions_on_one_finding_are_all_preserved_in_order(memory_engine):
    ev = _event(); write_event(memory_engine, ev)
    f = _finding(ev.id); write_finding(memory_engine, f)
    d1 = _decision(f.id, decision=DecisionOutcome.REFERRED, note="escalate")
    d2 = _decision(f.id, decision=DecisionOutcome.OVERRIDDEN, overridden_verdict=Verdict.NEEDS_REVIEW, note="1st")
    d3 = _decision(f.id, decision=DecisionOutcome.OVERRIDDEN, overridden_verdict=Verdict.COMPLIANT, note="2nd")
    for d in (d1, d2, d3):
        write_decision(memory_engine, d)
    with memory_engine.connect() as conn:
        rows = conn.execute(
            select(decisions).where(decisions.c.finding_id == f.id).order_by(text("rowid"))
        ).all()
    assert [r.id for r in rows] == [d1.id, d2.id, d3.id]
    assert [r.decision for r in rows] == ["REFERRED", "OVERRIDDEN", "OVERRIDDEN"]
    assert rows[-1].overridden_verdict == "COMPLIANT"
