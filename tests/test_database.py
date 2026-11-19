"""
Engine-factory tests: write/read-only/memory engines, WAL mode,
busy_timeout, foreign_keys pragma, and sqlite URI construction for
the read-only path (Architecture Proposal v4, Sections 2 and 5).
"""
from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import OperationalError

from shared.database import (
    _to_sqlite_readonly_uri,
    create_memory_engine,
    create_readonly_engine,
    create_write_engine,
)
from shared.exceptions import DatabaseConfigError
from shared.schema import events, init_database


# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------


def test_init_database_creates_all_three_tables(memory_engine):
    with memory_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ).fetchall()
    table_names = {r[0] for r in rows}
    assert {"events", "findings", "decisions"}.issubset(table_names)


def test_init_database_is_idempotent(memory_engine):
    # Calling init_database a second time on an already-initialised
    # engine must not raise (CREATE TABLE/TRIGGER IF NOT EXISTS).
    init_database(memory_engine)
    with memory_engine.connect() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    assert len(rows) >= 3


def test_foreign_keys_pragma_is_enabled_on_every_connection(memory_engine):
    with memory_engine.connect() as conn:
        value = conn.execute(text("PRAGMA foreign_keys")).scalar()
    assert value == 1


def test_busy_timeout_pragma_is_applied(memory_engine):
    with memory_engine.connect() as conn:
        value = conn.execute(text("PRAGMA busy_timeout")).scalar()
    assert value == 30_000


def test_wal_mode_is_set_on_file_backed_database(file_db):
    db_path, engine = file_db
    with engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()
    assert mode.lower() == "wal"


# ---------------------------------------------------------------------------
# Read-only engine
# ---------------------------------------------------------------------------


def test_readonly_engine_rejects_missing_database_file(tmp_path):
    missing_path = str(tmp_path / "does_not_exist.db")
    with pytest.raises(DatabaseConfigError):
        create_readonly_engine(missing_path)


def test_readonly_engine_allows_select(seeded_file_db):
    db_path, _write_engine = seeded_file_db
    ro_engine = create_readonly_engine(db_path)
    with ro_engine.connect() as conn:
        rows = conn.execute(select(events)).fetchall()
    assert len(rows) == 1
    assert rows[0].id == "seed-e1"


def test_readonly_engine_rejects_insert(seeded_file_db):
    db_path, _write_engine = seeded_file_db
    ro_engine = create_readonly_engine(db_path)
    with pytest.raises(OperationalError, match="readonly"):
        with ro_engine.begin() as conn:
            conn.execute(
                insert(events).values(
                    id="e-new", session_id="sess-seed", timestamp="t",
                    agent_name="a", action="run", status="started",
                )
            )


def test_readonly_engine_rejects_update(seeded_file_db):
    from sqlalchemy import update

    from shared.schema import events as events_tbl

    db_path, _write_engine = seeded_file_db
    ro_engine = create_readonly_engine(db_path)
    with pytest.raises(OperationalError):
        with ro_engine.begin() as conn:
            conn.execute(update(events_tbl).where(events_tbl.c.id == "seed-e1").values(action="x"))


def test_readonly_engine_rejects_delete(seeded_file_db):
    from sqlalchemy import delete

    from shared.schema import events as events_tbl

    db_path, _write_engine = seeded_file_db
    ro_engine = create_readonly_engine(db_path)
    with pytest.raises(OperationalError):
        with ro_engine.begin() as conn:
            conn.execute(delete(events_tbl).where(events_tbl.c.id == "seed-e1"))


def test_readonly_engine_query_only_pragma_is_set(seeded_file_db):
    db_path, _write_engine = seeded_file_db
    ro_engine = create_readonly_engine(db_path)
    with ro_engine.connect() as conn:
        value = conn.execute(text("PRAGMA query_only")).scalar()
    assert value == 1


def test_readonly_engine_sees_writes_made_via_write_engine_wal(seeded_file_db):
    """WAL mode must allow the read-only connection to see
    committed writes from the write engine without lock errors."""
    db_path, write_engine = seeded_file_db
    ro_engine = create_readonly_engine(db_path)

    with write_engine.begin() as conn:
        conn.execute(
            insert(events).values(
                id="seed-e2", session_id="sess-seed", timestamp="t2",
                agent_name="a", action="second", status="started",
            )
        )

    with ro_engine.connect() as conn:
        rows = conn.execute(select(events)).fetchall()
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# Read-only URI construction (string-level; see note in database.py
# about the Windows branch not being exercised end-to-end here)
# ---------------------------------------------------------------------------


def test_readonly_uri_for_posix_absolute_path():
    uri = _to_sqlite_readonly_uri("/tmp/some/path/audit.db")
    assert uri.startswith("file:/")
    assert uri.endswith("?mode=ro")
    assert "audit.db" in uri


def test_readonly_uri_for_windows_drive_letter_path_forward_slashes():
    # Windows path syntax (forward slashes), exercised as a pure
    # string-construction check: _to_sqlite_readonly_uri performs no
    # filesystem resolution and does not depend on the host OS's
    # pathlib flavour, so this is a valid check even though this test
    # suite runs on a Linux VM (see database.py's module docstring).
    uri = _to_sqlite_readonly_uri("C:/4IR 2026/Container Closure Agent S6/data/audit.db")
    assert uri.startswith("file:/C:/")
    assert "mode=ro" in uri
    assert "audit.db" in uri


def test_readonly_uri_for_windows_drive_letter_path_backslashes():
    # The native Windows path form, as it would actually arrive from
    # pathlib.Path(...).resolve() on a real Windows host (WindowsPath
    # stringifies with backslashes before .as_posix() is applied --
    # create_readonly_engine() always converts via resolved path
    # string, but this confirms the raw backslash form is also
    # handled correctly, independent of that call site).
    uri = _to_sqlite_readonly_uri(r"C:\4IR 2026\Container Closure Agent S6\data\audit.db")
    assert uri.startswith("file:/C:/")
    assert "mode=ro" in uri
    assert "\\" not in uri  # backslashes must be normalized to forward slashes


def test_readonly_uri_percent_encodes_spaces():
    uri = _to_sqlite_readonly_uri("/tmp/has space/audit.db")
    assert " " not in uri
    assert "%20" in uri


def test_sqlite3_itself_accepts_the_constructed_uri_on_this_platform(tmp_path):
    """End-to-end confirmation that the URI this function builds is
    one sqlite3.connect(uri=True) actually accepts, on whatever
    platform this test suite is running on (Linux, in this
    environment). This exercises the POSIX branch; the Windows
    drive-letter branch is covered only by string-level assertions
    above pending a real Windows smoke test (see Section 12 of the
    Phase 1 report)."""
    db_path = tmp_path / "audit.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()

    uri = _to_sqlite_readonly_uri(str(db_path))
    ro_conn = sqlite3.connect(uri, uri=True)
    cursor = ro_conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    assert cursor.fetchone()[0] == "t"
    with pytest.raises(sqlite3.OperationalError):
        ro_conn.execute("INSERT INTO t VALUES (1)")
    ro_conn.close()


# ---------------------------------------------------------------------------
# Write engine / memory engine basics
# ---------------------------------------------------------------------------


def test_write_engine_allows_insert_and_select(file_db):
    db_path, engine = file_db
    with engine.begin() as conn:
        conn.execute(
            insert(events).values(
                id="e1", session_id="s1", timestamp="t",
                agent_name="a", action="run", status="started",
            )
        )
    with engine.connect() as conn:
        row = conn.execute(select(events)).fetchone()
    assert row.id == "e1"


def test_memory_engine_shares_state_across_connections():
    engine = create_memory_engine()
    init_database(engine)
    with engine.begin() as conn:
        conn.execute(
            insert(events).values(
                id="e1", session_id="s1", timestamp="t",
                agent_name="a", action="run", status="started",
            )
        )
    # a second, separate connection from the SAME engine must see the row
    with engine.connect() as conn:
        row = conn.execute(select(events)).fetchone()
    assert row is not None
