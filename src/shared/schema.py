"""
SQLAlchemy Core schema for the shared Tier 0 audit database:
events, findings, decisions.

Design notes (Architecture Proposal v4):

* Relationship direction is one-way and non-circular:
      events (self-referential via parent_event_id)
        <- findings (via event_id)
          <- decisions (via finding_id)
  `events` has no column referencing `findings`.

* Every cross-table foreign key is a COMPOSITE key that includes
  session_id, so that a finding cannot reference an event belonging
  to a different session, and a decision cannot reference a finding
  belonging to a different session. SQLite resolves a composite FK
  against a UNIQUE constraint on the parent table's referenced
  columns, so `events` and `findings` each carry an explicit
  UniqueConstraint on (id, session_id) in addition to their primary
  key on id alone.

* All three tables are append-only: BEFORE UPDATE and BEFORE DELETE
  triggers unconditionally raise, so no row can be silently modified
  or removed via ordinary SQL, regardless of which code path
  attempts it. See _create_append_only_triggers().

* Timestamps are stored as TEXT in ISO-8601 with an explicit UTC "Z"
  suffix. `created_at` columns default to
  strftime('%Y-%m-%dT%H:%M:%fZ','now') at the database level, as a
  fallback audit trail even if application code's own `timestamp`
  value (from shared/models.py) were ever missing -- in normal
  operation both should agree.
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    ForeignKeyConstraint,
    Index,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.engine import Connection, Engine

metadata = MetaData()

_UTC_DEFAULT = text("(strftime('%Y-%m-%dT%H:%M:%fZ','now'))")

# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------

events = Table(
    "events",
    metadata,
    Column("id", String, primary_key=True),
    Column("session_id", String, nullable=False),
    Column("timestamp", String, nullable=False),
    Column("agent_name", String, nullable=False),
    Column("action", String, nullable=False),
    Column("status", String, nullable=False),
    Column("parent_event_id", String, nullable=True),
    Column("detail", Text, nullable=False, server_default="{}"),
    Column("created_at", String, nullable=False, server_default=_UTC_DEFAULT),
    UniqueConstraint("id", "session_id", name="uq_events_id_session"),
    ForeignKeyConstraint(
        ["parent_event_id", "session_id"],
        ["events.id", "events.session_id"],
        name="fk_events_parent_session",
        ondelete="RESTRICT",
    ),
)

Index("ix_events_session_id", events.c.session_id)
Index("ix_events_agent_name", events.c.agent_name)
Index("ix_events_timestamp", events.c.timestamp)
Index("ix_events_parent_event_id", events.c.parent_event_id)

# ---------------------------------------------------------------------------
# findings
# ---------------------------------------------------------------------------

findings = Table(
    "findings",
    metadata,
    Column("id", String, primary_key=True),
    Column("event_id", String, nullable=False),
    Column("session_id", String, nullable=False),
    Column("timestamp", String, nullable=False),
    Column("agent_name", String, nullable=False),
    Column("finding_type", String, nullable=False, server_default="compliance"),
    Column("section", String, nullable=False),
    Column("claim_text", Text, nullable=True),
    Column("claim_id", String, nullable=True),
    Column("requirement", Text, nullable=True),
    Column("requirement_id", String, nullable=True),
    Column("verdict", String, nullable=False),
    Column("severity", String, nullable=False),
    Column("citation", Text, nullable=True),
    Column("rationale", Text, nullable=False),
    Column("linked_sections", Text, nullable=False, server_default="[]"),
    Column("source_refs", Text, nullable=False, server_default="[]"),
    Column("detail", Text, nullable=False, server_default="{}"),
    Column("created_at", String, nullable=False, server_default=_UTC_DEFAULT),
    UniqueConstraint("id", "session_id", name="uq_findings_id_session"),
    ForeignKeyConstraint(
        ["event_id", "session_id"],
        ["events.id", "events.session_id"],
        name="fk_findings_event_session",
        ondelete="RESTRICT",
    ),
)

Index("ix_findings_event_id", findings.c.event_id)
Index("ix_findings_session_id", findings.c.session_id)
Index("ix_findings_agent_name", findings.c.agent_name)
Index("ix_findings_verdict", findings.c.verdict)
Index("ix_findings_section", findings.c.section)
Index("ix_findings_finding_type", findings.c.finding_type)
Index("ix_findings_timestamp", findings.c.timestamp)

# ---------------------------------------------------------------------------
# decisions
# ---------------------------------------------------------------------------

decisions = Table(
    "decisions",
    metadata,
    Column("id", String, primary_key=True),
    Column("finding_id", String, nullable=False),
    Column("session_id", String, nullable=False),
    Column("timestamp", String, nullable=False),
    Column("gate_name", String, nullable=False),
    Column("assessor", String, nullable=False),
    Column("decision", String, nullable=False),
    Column("note", Text, nullable=False),
    Column("overridden_verdict", String, nullable=True),
    Column("created_at", String, nullable=False, server_default=_UTC_DEFAULT),
    ForeignKeyConstraint(
        ["finding_id", "session_id"],
        ["findings.id", "findings.session_id"],
        name="fk_decisions_finding_session",
        ondelete="RESTRICT",
    ),
)

Index("ix_decisions_finding_id", decisions.c.finding_id)
Index("ix_decisions_session_id", decisions.c.session_id)
Index("ix_decisions_timestamp", decisions.c.timestamp)

# ---------------------------------------------------------------------------
# Append-only triggers
# ---------------------------------------------------------------------------

_AUDIT_TABLES = ("events", "findings", "decisions")


def _append_only_trigger_statements() -> list[str]:
    statements: list[str] = []
    for table_name in _AUDIT_TABLES:
        statements.append(
            f"""
            CREATE TRIGGER IF NOT EXISTS {table_name}_no_update
            BEFORE UPDATE ON {table_name}
            BEGIN
                SELECT RAISE(ABORT, 'Audit records are append-only: UPDATE not permitted on {table_name}');
            END;
            """
        )
        statements.append(
            f"""
            CREATE TRIGGER IF NOT EXISTS {table_name}_no_delete
            BEFORE DELETE ON {table_name}
            BEGIN
                SELECT RAISE(ABORT, 'Audit records are append-only: DELETE not permitted on {table_name}');
            END;
            """
        )
    return statements


def _create_append_only_triggers(conn: Connection) -> None:
    for statement in _append_only_trigger_statements():
        conn.execute(text(statement))


def init_database(engine: Engine) -> None:
    """Create all tables (if not already present) and install the
    append-only triggers. Idempotent -- safe to call on an
    already-initialised database (CREATE TABLE IF NOT EXISTS /
    CREATE TRIGGER IF NOT EXISTS semantics throughout).

    WAL mode is set here explicitly (in addition to being set on
    every connection's pragmas in shared/database.py, where it is a
    no-op after the first time) because journal_mode=WAL is a
    database-level, persistent setting that only needs to be written
    once, not per-connection.
    """
    with engine.begin() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
    metadata.create_all(engine)
    with engine.begin() as conn:
        _create_append_only_triggers(conn)
