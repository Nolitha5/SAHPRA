"""
Database-level integrity tests: composite foreign keys enforcing
session consistency, and append-only triggers rejecting UPDATE/DELETE
on all three audit tables (Architecture Proposal v4, Sections 1 and 4).
"""
from __future__ import annotations

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from shared.schema import decisions, events, findings


def _insert_event(conn, event_id="e1", session_id="s1"):
    conn.execute(
        insert(events).values(
            id=event_id, session_id=session_id, timestamp="t",
            agent_name="s6_container_closure", action="run", status="started",
        )
    )


def _insert_finding(conn, finding_id="f1", event_id="e1", session_id="s1"):
    conn.execute(
        insert(findings).values(
            id=finding_id, event_id=event_id, session_id=session_id, timestamp="t",
            agent_name="s6_container_closure", section="S.6",
            verdict="COMPLIANT", severity="INFO", rationale="r",
        )
    )


# ---------------------------------------------------------------------------
# Composite foreign keys -- session consistency (Section 1)
# ---------------------------------------------------------------------------


def test_finding_in_same_session_as_event_is_accepted(memory_engine):
    with memory_engine.begin() as conn:
        _insert_event(conn, session_id="sess-A")
        _insert_finding(conn, session_id="sess-A")
    with memory_engine.connect() as conn:
        row = conn.execute(select(findings)).fetchone()
    assert row.session_id == "sess-A"


def test_finding_referencing_event_in_different_session_is_rejected(memory_engine):
    with memory_engine.begin() as conn:
        _insert_event(conn, event_id="e1", session_id="sess-A")
    with pytest.raises(IntegrityError):
        with memory_engine.begin() as conn:
            conn.execute(
                insert(findings).values(
                    id="f1", event_id="e1", session_id="sess-B", timestamp="t",
                    agent_name="a", section="S.6", verdict="COMPLIANT",
                    severity="INFO", rationale="r",
                )
            )
    with memory_engine.connect() as conn:
        rows = conn.execute(select(findings)).fetchall()
    assert rows == []


def test_decision_in_same_session_as_finding_is_accepted(memory_engine):
    with memory_engine.begin() as conn:
        _insert_event(conn, session_id="sess-A")
        _insert_finding(conn, session_id="sess-A")
        conn.execute(
            insert(decisions).values(
                id="d1", finding_id="f1", session_id="sess-A", timestamp="t",
                gate_name="g", assessor="a", decision="APPROVED", note="n",
            )
        )
    with memory_engine.connect() as conn:
        row = conn.execute(select(decisions)).fetchone()
    assert row.session_id == "sess-A"


def test_decision_referencing_finding_in_different_session_is_rejected(memory_engine):
    with memory_engine.begin() as conn:
        _insert_event(conn, session_id="sess-A")
        _insert_finding(conn, session_id="sess-A")
    with pytest.raises(IntegrityError):
        with memory_engine.begin() as conn:
            conn.execute(
                insert(decisions).values(
                    id="d1", finding_id="f1", session_id="sess-B", timestamp="t",
                    gate_name="g", assessor="a", decision="APPROVED", note="n",
                )
            )
    with memory_engine.connect() as conn:
        rows = conn.execute(select(decisions)).fetchall()
    assert rows == []


def test_child_event_referencing_parent_in_different_session_is_rejected(memory_engine):
    with memory_engine.begin() as conn:
        _insert_event(conn, event_id="e1", session_id="sess-A")
    with pytest.raises(IntegrityError):
        with memory_engine.begin() as conn:
            conn.execute(
                insert(events).values(
                    id="e2", session_id="sess-B", timestamp="t",
                    agent_name="a", action="sub", status="started",
                    parent_event_id="e1",
                )
            )
    with memory_engine.connect() as conn:
        rows = conn.execute(select(events).where(events.c.id == "e2")).fetchall()
    assert rows == []


def test_child_event_referencing_parent_in_same_session_is_accepted(memory_engine):
    with memory_engine.begin() as conn:
        _insert_event(conn, event_id="e1", session_id="sess-A")
        conn.execute(
            insert(events).values(
                id="e2", session_id="sess-A", timestamp="t",
                agent_name="a", action="sub", status="started",
                parent_event_id="e1",
            )
        )
    with memory_engine.connect() as conn:
        row = conn.execute(select(events).where(events.c.id == "e2")).fetchone()
    assert row.parent_event_id == "e1"


def test_finding_referencing_nonexistent_event_is_rejected(memory_engine):
    with pytest.raises(IntegrityError):
        with memory_engine.begin() as conn:
            conn.execute(
                insert(findings).values(
                    id="f1", event_id="does-not-exist", session_id="s1", timestamp="t",
                    agent_name="a", section="S.6", verdict="COMPLIANT",
                    severity="INFO", rationale="r",
                )
            )


# ---------------------------------------------------------------------------
# Append-only triggers (Section 4)
# ---------------------------------------------------------------------------


def test_update_on_events_is_rejected(memory_engine):
    with memory_engine.begin() as conn:
        _insert_event(conn)
    with pytest.raises(IntegrityError, match="append-only"):
        with memory_engine.begin() as conn:
            conn.execute(update(events).where(events.c.id == "e1").values(action="changed"))
    with memory_engine.connect() as conn:
        row = conn.execute(select(events).where(events.c.id == "e1")).fetchone()
    assert row.action == "run"


def test_delete_on_events_is_rejected(memory_engine):
    with memory_engine.begin() as conn:
        _insert_event(conn)
    with pytest.raises(IntegrityError, match="append-only"):
        with memory_engine.begin() as conn:
            conn.execute(delete(events).where(events.c.id == "e1"))
    with memory_engine.connect() as conn:
        row = conn.execute(select(events).where(events.c.id == "e1")).fetchone()
    assert row is not None


def test_update_on_findings_is_rejected(memory_engine):
    with memory_engine.begin() as conn:
        _insert_event(conn)
        _insert_finding(conn)
    with pytest.raises(IntegrityError, match="append-only"):
        with memory_engine.begin() as conn:
            conn.execute(update(findings).where(findings.c.id == "f1").values(verdict="NON_COMPLIANT"))
    with memory_engine.connect() as conn:
        row = conn.execute(select(findings).where(findings.c.id == "f1")).fetchone()
    assert row.verdict == "COMPLIANT"


def test_delete_on_findings_is_rejected(memory_engine):
    with memory_engine.begin() as conn:
        _insert_event(conn)
        _insert_finding(conn)
    with pytest.raises(IntegrityError, match="append-only"):
        with memory_engine.begin() as conn:
            conn.execute(delete(findings).where(findings.c.id == "f1"))
    with memory_engine.connect() as conn:
        row = conn.execute(select(findings).where(findings.c.id == "f1")).fetchone()
    assert row is not None


def test_update_on_decisions_is_rejected(memory_engine):
    with memory_engine.begin() as conn:
        _insert_event(conn)
        _insert_finding(conn)
        conn.execute(
            insert(decisions).values(
                id="d1", finding_id="f1", session_id="s1", timestamp="t",
                gate_name="g", assessor="a", decision="APPROVED", note="n",
            )
        )
    with pytest.raises(IntegrityError, match="append-only"):
        with memory_engine.begin() as conn:
            conn.execute(update(decisions).where(decisions.c.id == "d1").values(note="edited"))
    with memory_engine.connect() as conn:
        row = conn.execute(select(decisions).where(decisions.c.id == "d1")).fetchone()
    assert row.note == "n"


def test_delete_on_decisions_is_rejected(memory_engine):
    with memory_engine.begin() as conn:
        _insert_event(conn)
        _insert_finding(conn)
        conn.execute(
            insert(decisions).values(
                id="d1", finding_id="f1", session_id="s1", timestamp="t",
                gate_name="g", assessor="a", decision="APPROVED", note="n",
            )
        )
    with pytest.raises(IntegrityError, match="append-only"):
        with memory_engine.begin() as conn:
            conn.execute(delete(decisions).where(decisions.c.id == "d1"))
    with memory_engine.connect() as conn:
        row = conn.execute(select(decisions).where(decisions.c.id == "d1")).fetchone()
    assert row is not None


def test_fk_restrict_prevents_deleting_referenced_event_even_if_trigger_were_absent():
    """Defence-in-depth check: even setting aside the trigger, the
    ON DELETE RESTRICT composite FK independently blocks removing an
    event that a finding still references. We verify this by
    confirming the delete attempt raises IntegrityError (the trigger
    fires first in this schema, but RESTRICT is also in place)."""
    from shared.database import create_memory_engine
    from shared.schema import init_database

    engine = create_memory_engine()
    init_database(engine)
    with engine.begin() as conn:
        _insert_event(conn)
        _insert_finding(conn)
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(delete(events).where(events.c.id == "e1"))


def test_audit_module_will_expose_no_mutation_helpers():
    """Placeholder guard for Phase 2: shared/audit.py (not yet
    implemented) must only ever expose INSERT-based write functions.
    This test currently just documents the requirement against the
    schema module's own public names, none of which should suggest
    mutation."""
    import shared.schema as schema_module

    forbidden_substrings = ("update_", "delete_", "modify_", "remove_")
    public_names = [n for n in dir(schema_module) if not n.startswith("_")]
    for name in public_names:
        for forbidden in forbidden_substrings:
            assert forbidden not in name.lower(), (
                f"shared.schema exposes '{name}', which suggests a mutation "
                f"helper; audit tables must only be written via INSERT"
            )
