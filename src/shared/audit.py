"""
Shared audit WRITE layer for the Container Closure Agent S6 project
(Tier 0, Phase 2).

This module is the ONLY sanctioned way to put rows into the
`events`, `findings` and `decisions` tables. It exposes exactly three
primitive write functions -- write_event(), write_finding(),
write_decision() -- plus one convenience context manager,
execution_scope(), that composes write_event() into the
started -> completed/failed lifecycle described in Architecture
Proposal v4, Section 6.

Design rules (all enforced here, in addition to the database-level
constraints already installed by shared/schema.py):

* INSERT only. There is no update or delete function here, and none
  will be added; the append-only triggers in shared/schema.py reject
  UPDATE/DELETE regardless of what any caller attempts.
* Every write runs inside a single transaction (engine.begin()).
  Pre-write reference checks and the INSERT share that transaction,
  so a failure at any point rolls the whole thing back and nothing
  partial is ever committed.
* Referential problems are detected BEFORE the INSERT and reported
  with a specific, human-readable AuditWriteError (which event is
  missing, which session mismatched, which id is duplicated). The
  composite foreign keys and primary keys in the schema remain the
  authoritative backstop: if a check here were ever bypassed, SQLite
  would still reject the row, and that IntegrityError is also mapped
  to AuditWriteError.
* Models are serialised with model_dump(mode="json"), so enum fields
  land as their string values and the `timestamp` field goes through
  the UTC "...Z" millisecond serializer defined in shared/models.py.
  JSON-typed columns (detail, linked_sections, source_refs) are
  stored as JSON text.

On terminal events and crashes: execution_scope() writes a `failed`
terminal event for any exception that propagates out of its body,
and a `completed` event otherwise. That covers *handled* failures --
exceptions Python can observe. It does NOT and cannot cover a process
that is killed, loses power, or segfaults mid-scope: in that case the
`started` event will have no terminal partner. Consumers reconstructing
a session timeline must therefore treat a `started` event with no
matching terminal event as "outcome unknown", not as "still running".
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError, OperationalError

from .enums import AgentName, EventStatus
from .exceptions import AuditWriteError
from .models import AuditEvent, FindingRecord, HumanGateDecision
from .schema import decisions, events, findings

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _event_session(conn: Connection, event_id: str) -> str | None:
    """Return the session_id of the event with this id, or None if
    no such event exists."""
    return conn.execute(
        select(events.c.session_id).where(events.c.id == event_id)
    ).scalar_one_or_none()


def _finding_session(conn: Connection, finding_id: str) -> str | None:
    return conn.execute(
        select(findings.c.session_id).where(findings.c.id == finding_id)
    ).scalar_one_or_none()


def _decision_exists(conn: Connection, decision_id: str) -> bool:
    return (
        conn.execute(
            select(decisions.c.id).where(decisions.c.id == decision_id)
        ).scalar_one_or_none()
        is not None
    )


def _require_same_session(
    *, kind: str, ref_id: str, ref_session: str | None, own_session: str
) -> None:
    """Raise a specific AuditWriteError if a referenced row is missing
    or belongs to a different session."""
    if ref_session is None:
        raise AuditWriteError(
            f"referenced {kind} '{ref_id}' does not exist"
        )
    if ref_session != own_session:
        raise AuditWriteError(
            f"referenced {kind} '{ref_id}' belongs to session "
            f"'{ref_session}', not to session '{own_session}' "
            f"(cross-session references are not permitted)"
        )


def _wrap_db_error(exc: Exception, what: str) -> AuditWriteError:
    """Translate a SQLAlchemy/sqlite3 error raised during an INSERT
    into an AuditWriteError with the original message preserved."""
    original = getattr(exc, "orig", exc)
    return AuditWriteError(f"failed to write {what}: {original}")


# ---------------------------------------------------------------------------
# write_event
# ---------------------------------------------------------------------------


def write_event(engine: Engine, event: AuditEvent) -> str:
    """Insert one audit event. Returns the event id.

    Validation before insert (inside the same transaction):
    * event.id must not already exist.
    * If parent_event_id is set, that event must exist and must be
      in the same session as this event.

    Raises AuditWriteError on any validation or database failure;
    the transaction is rolled back and no row is written.
    """
    payload = event.model_dump(mode="json")
    try:
        with engine.begin() as conn:
            if _event_session(conn, event.id) is not None:
                raise AuditWriteError(
                    f"event id '{event.id}' already exists (ids must be unique)"
                )
            if event.parent_event_id is not None:
                _require_same_session(
                    kind="parent event",
                    ref_id=event.parent_event_id,
                    ref_session=_event_session(conn, event.parent_event_id),
                    own_session=event.session_id,
                )
            conn.execute(
                insert(events).values(
                    id=payload["id"],
                    session_id=payload["session_id"],
                    timestamp=payload["timestamp"],
                    agent_name=payload["agent_name"],
                    action=payload["action"],
                    status=payload["status"],
                    parent_event_id=payload["parent_event_id"],
                    detail=_json(payload["detail"]),
                )
            )
    except AuditWriteError:
        raise
    except (IntegrityError, OperationalError) as exc:
        raise _wrap_db_error(exc, f"event '{event.id}'") from exc
    return event.id


# ---------------------------------------------------------------------------
# write_finding
# ---------------------------------------------------------------------------


def write_finding(engine: Engine, finding: FindingRecord) -> str:
    """Insert one finding. Returns the finding id.

    Validation before insert (inside the same transaction):
    * finding.id must not already exist.
    * finding.event_id must reference an existing event in the SAME
      session as the finding (every finding is traceable to the
      execution event that produced it).

    The Pydantic rules on FindingRecord (e.g. a NON_COMPLIANT
    contradiction must carry a citation) have already run by the
    time a FindingRecord instance exists; this function does not
    re-implement them.
    """
    payload = finding.model_dump(mode="json")
    try:
        with engine.begin() as conn:
            if _finding_session(conn, finding.id) is not None:
                raise AuditWriteError(
                    f"finding id '{finding.id}' already exists (ids must be unique)"
                )
            _require_same_session(
                kind="event",
                ref_id=finding.event_id,
                ref_session=_event_session(conn, finding.event_id),
                own_session=finding.session_id,
            )
            conn.execute(
                insert(findings).values(
                    id=payload["id"],
                    event_id=payload["event_id"],
                    session_id=payload["session_id"],
                    timestamp=payload["timestamp"],
                    agent_name=payload["agent_name"],
                    finding_type=payload["finding_type"],
                    section=payload["section"],
                    claim_text=payload["claim_text"],
                    claim_id=payload["claim_id"],
                    requirement=payload["requirement"],
                    requirement_id=payload["requirement_id"],
                    verdict=payload["verdict"],
                    severity=payload["severity"],
                    citation=payload["citation"],
                    rationale=payload["rationale"],
                    linked_sections=_json(payload["linked_sections"]),
                    source_refs=_json(payload["source_refs"]),
                    detail=_json(payload["detail"]),
                )
            )
    except AuditWriteError:
        raise
    except (IntegrityError, OperationalError) as exc:
        raise _wrap_db_error(exc, f"finding '{finding.id}'") from exc
    return finding.id


# ---------------------------------------------------------------------------
# write_decision
# ---------------------------------------------------------------------------


def write_decision(engine: Engine, decision: HumanGateDecision) -> str:
    """Insert one Human Gate decision. Returns the decision id.

    Validation before insert (inside the same transaction):
    * decision.id must not already exist.
    * decision.finding_id must reference an existing finding in the
      SAME session as the decision.

    Override semantics are preserved by construction: this is an
    INSERT of a new decisions row, the referenced finding row is
    never touched (and the schema's triggers would reject any attempt
    to touch it), and every subsequent decision on the same finding
    is a further new row. The OVERRIDDEN <-> overridden_verdict
    pairing rule is enforced by the HumanGateDecision model before
    this function is ever reached.
    """
    payload = decision.model_dump(mode="json")
    try:
        with engine.begin() as conn:
            if _decision_exists(conn, decision.id):
                raise AuditWriteError(
                    f"decision id '{decision.id}' already exists (ids must be unique)"
                )
            _require_same_session(
                kind="finding",
                ref_id=decision.finding_id,
                ref_session=_finding_session(conn, decision.finding_id),
                own_session=decision.session_id,
            )
            conn.execute(
                insert(decisions).values(
                    id=payload["id"],
                    finding_id=payload["finding_id"],
                    session_id=payload["session_id"],
                    timestamp=payload["timestamp"],
                    gate_name=payload["gate_name"],
                    assessor=payload["assessor"],
                    decision=payload["decision"],
                    note=payload["note"],
                    overridden_verdict=payload["overridden_verdict"],
                )
            )
    except AuditWriteError:
        raise
    except (IntegrityError, OperationalError) as exc:
        raise _wrap_db_error(exc, f"decision '{decision.id}'") from exc
    return decision.id


# ---------------------------------------------------------------------------
# Lifecycle helper
# ---------------------------------------------------------------------------


@contextmanager
def execution_scope(
    engine: Engine,
    *,
    session_id: str,
    agent_name: AgentName,
    action: str,
    parent_event_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> Iterator[AuditEvent]:
    """Write a `started` event, yield it, then write the matching
    terminal event.

    * Body completes normally  -> a `completed` event whose
      parent_event_id is the started event's id.
    * Body raises              -> a `failed` event (same parent link)
      whose detail records the exception type and message; the
      original exception is then re-raised unchanged.

    Findings produced inside the scope should reference the yielded
    started event's id as their event_id (Architecture Proposal v4,
    Section 6: findings point at the execution event that produced
    them).

    Limits: this only guarantees a terminal event for exceptions
    Python can observe. A hard process crash, kill -9, or power loss
    inside the body leaves the `started` event without a terminal
    partner. See the module docstring.

    If writing the `failed` terminal event itself fails (for example,
    the database became unavailable), the original exception is still
    the one re-raised -- the caller must see the real cause. The
    secondary AuditWriteError is attached to it as the attribute
    `audit_terminal_write_error` so it is not silently lost.
    """
    started = AuditEvent(
        session_id=session_id,
        agent_name=agent_name,
        action=action,
        status=EventStatus.STARTED,
        parent_event_id=parent_event_id,
        detail=detail or {},
    )
    write_event(engine, started)

    try:
        yield started
    except BaseException as exc:
        try:
            write_event(
                engine,
                AuditEvent(
                    session_id=session_id,
                    agent_name=agent_name,
                    action=action,
                    status=EventStatus.FAILED,
                    parent_event_id=started.id,
                    detail={
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                ),
            )
        except AuditWriteError as terminal_write_error:
            # Keep the original failure as the primary exception, but
            # do not lose the fact that the audit trail is now missing
            # its terminal event.
            exc.audit_terminal_write_error = terminal_write_error  # type: ignore[attr-defined]
        raise

    write_event(
        engine,
        AuditEvent(
            session_id=session_id,
            agent_name=agent_name,
            action=action,
            status=EventStatus.COMPLETED,
            parent_event_id=started.id,
        ),
    )
