"""
Shared audit READ layer for the Container Closure Agent S6 project
(Tier 0, Phase 3).

This is the query surface intended for M4b's evaluation harness and
M5's UI, as well as for our own agents. Every function here issues
SELECT statements only.

Engine choice: callers outside this project's own agents should pass
an engine from shared.database.create_readonly_engine(), which opens
the file with SQLite's mode=ro flag so that writes are impossible at
the VFS level regardless of what SQL is attempted. The functions
themselves work with any engine (the test suite also runs them
against the in-memory engine), because they never write.

Session isolation: every lookup takes an explicit `session_id`. A
record that exists but belongs to a different session is reported as
not found -- a caller holding one session's id cannot discover or
read another session's records through this module.

Ordering: timelines and decision histories are ordered by
`timestamp`, with SQLite's `rowid` (insertion order) as a
deterministic tie-breaker, since `timestamp` has millisecond
precision and several rows can share a millisecond.

Effective verdict (Architecture Proposal v4, Section 4.2): the
finding's own `verdict` column is never changed. The effective
verdict is computed on read: if the MOST RECENT decision for the
finding is OVERRIDDEN, the effective verdict is that decision's
`overridden_verdict`; otherwise it is the finding's original verdict.
The full decision history is always available via
get_finding_decisions().

Unfinished events: a `started` event with no `completed`/`failed`
partner (a terminal event whose parent_event_id is the started
event's id) is reported with outcome "unknown". It is NOT classified
as failed -- the audit layer cannot distinguish "still running" from
"process died" (see shared/audit.py), and this module does not guess.
"""
from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ValidationError
from sqlalchemy import select, text
from sqlalchemy.engine import Connection, Engine, Row
from sqlalchemy.exc import SQLAlchemyError

from .enums import DecisionOutcome, FindingType, Verdict
from .exceptions import AuditQueryError
from .models import AuditEvent, FindingRecord, HumanGateDecision
from .schema import decisions, events, findings

# ---------------------------------------------------------------------------
# Exceptions and result models local to the query layer
# ---------------------------------------------------------------------------


class AuditNotFoundError(AuditQueryError):
    """A requested record does not exist in the given session. Kept as
    a subclass so callers (e.g. an M5 endpoint) can distinguish
    "no such record" from a genuine database failure, both of which
    are still AuditQueryError."""


class EffectiveVerdict(BaseModel):
    """Result of get_effective_verdict(). `original_verdict` is the
    finding's stored verdict and is never altered; `effective_verdict`
    is what a reader should act on after applying override semantics."""

    finding_id: str
    session_id: str
    original_verdict: Verdict
    effective_verdict: Verdict
    overridden: bool
    overriding_decision_id: str | None = None
    decision_count: int


class UnfinishedEvent(BaseModel):
    """A `started` event with no terminal partner. The outcome is
    unknown by construction -- this model deliberately has no way to
    express "failed"."""

    event: AuditEvent
    outcome: Literal["unknown"] = "unknown"


# ---------------------------------------------------------------------------
# Row -> model conversion
# ---------------------------------------------------------------------------


def _loads(value: str | None, default: Any) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


def _event_from_row(row: Row) -> AuditEvent:
    return AuditEvent(
        id=row.id,
        session_id=row.session_id,
        timestamp=row.timestamp,
        agent_name=row.agent_name,
        action=row.action,
        status=row.status,
        parent_event_id=row.parent_event_id,
        detail=_loads(row.detail, {}),
    )


def _finding_from_row(row: Row) -> FindingRecord:
    return FindingRecord(
        id=row.id,
        event_id=row.event_id,
        session_id=row.session_id,
        timestamp=row.timestamp,
        agent_name=row.agent_name,
        finding_type=row.finding_type,
        section=row.section,
        claim_text=row.claim_text,
        claim_id=row.claim_id,
        requirement=row.requirement,
        requirement_id=row.requirement_id,
        verdict=row.verdict,
        severity=row.severity,
        citation=row.citation,
        rationale=row.rationale,
        linked_sections=_loads(row.linked_sections, []),
        source_refs=_loads(row.source_refs, []),
        detail=_loads(row.detail, {}),
    )


def _decision_from_row(row: Row) -> HumanGateDecision:
    return HumanGateDecision(
        id=row.id,
        finding_id=row.finding_id,
        session_id=row.session_id,
        timestamp=row.timestamp,
        gate_name=row.gate_name,
        assessor=row.assessor,
        decision=row.decision,
        note=row.note,
        overridden_verdict=row.overridden_verdict,
    )


def _run(engine: Engine, what: str, fn):
    """Execute `fn(conn)` on a connection, translating database and
    model-validation failures into AuditQueryError. A failure to
    validate a stored row into its model means the database holds
    data the contracts do not accept -- that is reported, not
    silently skipped."""
    try:
        with engine.connect() as conn:
            return fn(conn)
    except AuditQueryError:
        raise
    except SQLAlchemyError as exc:
        original = getattr(exc, "orig", exc)
        raise AuditQueryError(f"query failed ({what}): {original}") from exc
    except (ValidationError, ValueError) as exc:
        raise AuditQueryError(
            f"stored record could not be validated ({what}): {exc}"
        ) from exc


_ROWID = text("rowid")

# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


def get_event(engine: Engine, event_id: str, *, session_id: str) -> AuditEvent:
    """Return one event. Raises AuditNotFoundError if no event with
    this id exists in this session."""

    def _q(conn: Connection) -> AuditEvent:
        row = conn.execute(
            select(events).where(events.c.id == event_id, events.c.session_id == session_id)
        ).one_or_none()
        if row is None:
            raise AuditNotFoundError(
                f"event '{event_id}' not found in session '{session_id}'"
            )
        return _event_from_row(row)

    return _run(engine, f"get_event {event_id}", _q)


def get_session_events(engine: Engine, session_id: str) -> list[AuditEvent]:
    """The full timeline for a session, oldest first. An unknown
    session simply yields an empty list -- there is no registry of
    sessions to check against."""

    def _q(conn: Connection) -> list[AuditEvent]:
        rows = conn.execute(
            select(events)
            .where(events.c.session_id == session_id)
            .order_by(events.c.timestamp, _ROWID)
        ).all()
        return [_event_from_row(r) for r in rows]

    return _run(engine, f"get_session_events {session_id}", _q)


def get_unfinished_events(engine: Engine, session_id: str) -> list[UnfinishedEvent]:
    """All `started` events in the session that have no terminal
    partner, i.e. no `completed`/`failed` event whose parent_event_id
    is the started event's id. Each is reported with outcome
    "unknown"."""

    def _q(conn: Connection) -> list[UnfinishedEvent]:
        terminal = events.alias("terminal")
        rows = conn.execute(
            select(events)
            .where(
                events.c.session_id == session_id,
                events.c.status == "started",
                ~select(terminal.c.id)
                .where(
                    terminal.c.parent_event_id == events.c.id,
                    terminal.c.session_id == session_id,
                    terminal.c.status.in_(("completed", "failed")),
                )
                .exists(),
            )
            .order_by(events.c.timestamp, _ROWID)
        ).all()
        return [UnfinishedEvent(event=_event_from_row(r)) for r in rows]

    return _run(engine, f"get_unfinished_events {session_id}", _q)


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


def get_finding(engine: Engine, finding_id: str, *, session_id: str) -> FindingRecord:
    """Return one finding. Raises AuditNotFoundError if no finding
    with this id exists in this session."""

    def _q(conn: Connection) -> FindingRecord:
        row = conn.execute(
            select(findings).where(
                findings.c.id == finding_id, findings.c.session_id == session_id
            )
        ).one_or_none()
        if row is None:
            raise AuditNotFoundError(
                f"finding '{finding_id}' not found in session '{session_id}'"
            )
        return _finding_from_row(row)

    return _run(engine, f"get_finding {finding_id}", _q)


def get_session_findings(
    engine: Engine,
    session_id: str,
    *,
    finding_type: FindingType | None = None,
) -> list[FindingRecord]:
    """All findings in a session, oldest first, optionally filtered
    to one finding_type (e.g. FindingType.CONTRADICTION)."""

    def _q(conn: Connection) -> list[FindingRecord]:
        stmt = select(findings).where(findings.c.session_id == session_id)
        if finding_type is not None:
            stmt = stmt.where(findings.c.finding_type == finding_type.value)
        rows = conn.execute(stmt.order_by(findings.c.timestamp, _ROWID)).all()
        return [_finding_from_row(r) for r in rows]

    return _run(engine, f"get_session_findings {session_id}", _q)


# ---------------------------------------------------------------------------
# Decisions and effective verdict
# ---------------------------------------------------------------------------


def _decision_rows(conn: Connection, finding_id: str, session_id: str) -> list[Row]:
    return conn.execute(
        select(decisions)
        .where(decisions.c.finding_id == finding_id, decisions.c.session_id == session_id)
        .order_by(decisions.c.timestamp, _ROWID)
    ).all()


def _require_finding_row(conn: Connection, finding_id: str, session_id: str) -> Row:
    row = conn.execute(
        select(findings).where(findings.c.id == finding_id, findings.c.session_id == session_id)
    ).one_or_none()
    if row is None:
        raise AuditNotFoundError(
            f"finding '{finding_id}' not found in session '{session_id}'"
        )
    return row


def get_finding_decisions(
    engine: Engine, finding_id: str, *, session_id: str
) -> list[HumanGateDecision]:
    """The complete, ordered Human Gate decision history for a
    finding (oldest first). Raises AuditNotFoundError if the finding
    itself does not exist in the session; returns [] if it exists but
    has no decisions yet."""

    def _q(conn: Connection) -> list[HumanGateDecision]:
        _require_finding_row(conn, finding_id, session_id)
        return [_decision_from_row(r) for r in _decision_rows(conn, finding_id, session_id)]

    return _run(engine, f"get_finding_decisions {finding_id}", _q)


def get_effective_verdict(
    engine: Engine, finding_id: str, *, session_id: str
) -> EffectiveVerdict:
    """Apply override semantics on read, without touching the
    finding. If the most recent decision is OVERRIDDEN, the effective
    verdict is its overridden_verdict; otherwise it is the finding's
    stored verdict."""

    def _q(conn: Connection) -> EffectiveVerdict:
        frow = _require_finding_row(conn, finding_id, session_id)
        history = _decision_rows(conn, finding_id, session_id)
        original = Verdict(frow.verdict)
        latest = history[-1] if history else None
        if latest is not None and latest.decision == DecisionOutcome.OVERRIDDEN.value:
            if latest.overridden_verdict is None:
                # The model forbids this combination at write time;
                # if it is present the database has been tampered with
                # or written by something other than shared.audit.
                raise AuditQueryError(
                    f"decision '{latest.id}' is OVERRIDDEN but has no "
                    f"overridden_verdict; stored data violates the "
                    f"HumanGateDecision contract"
                )
            return EffectiveVerdict(
                finding_id=finding_id,
                session_id=session_id,
                original_verdict=original,
                effective_verdict=Verdict(latest.overridden_verdict),
                overridden=True,
                overriding_decision_id=latest.id,
                decision_count=len(history),
            )
        return EffectiveVerdict(
            finding_id=finding_id,
            session_id=session_id,
            original_verdict=original,
            effective_verdict=original,
            overridden=False,
            overriding_decision_id=None,
            decision_count=len(history),
        )

    return _run(engine, f"get_effective_verdict {finding_id}", _q)
