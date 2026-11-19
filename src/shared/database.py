"""
SQLite/SQLAlchemy engine factories for the Container Closure Agent
S6 project.

Three distinct engines are provided, deliberately kept separate
rather than configured via flags on one function, because they have
different safety properties and different callers:

* create_write_engine(db_path)    -- used ONLY by our own agents
                                      (shared/audit.py, in a later
                                      phase). Full read/write.
* create_readonly_engine(db_path) -- given to M4b's evaluation
                                      harness and M5's UI. Opens the
                                      database file with SQLite's own
                                      mode=ro URI flag, so writes are
                                      rejected at the SQLite VFS
                                      layer itself -- not merely by
                                      application convention.
* create_memory_engine()          -- used by the test suite. An
                                      in-memory database shared across
                                      all connections via StaticPool
                                      (a plain ":memory:" database is
                                      otherwise a fresh, empty database
                                      on every new connection).

Implementation note on connection construction: both file-backed
engines use a `creator` callable that calls sqlite3.connect()
directly with a plain OS path (sqlite3 accepts Windows paths,
including drive letters and spaces, exactly as given), rather than
routing the path through a `sqlite:///...` SQLAlchemy URL. This is a
deliberate deviation from the most commonly shown SQLAlchemy sqlite
example. It avoids a real, environment-specific risk: this project's
own workspace path -- "C:\\4IR 2026\\Container Closure Agent S6" --
contains both a backslash-delimited Windows path and a literal space,
and SQLAlchemy's sqlite dialect expects to parse the text after
`sqlite:///` as part of a URL string. Going straight to
sqlite3.connect() with the raw path sidesteps any URL-escaping
ambiguity entirely for the write engine.

Implementation note on the read-only URI (_to_sqlite_readonly_uri):
this function deliberately does NOT call pathlib.Path(...).resolve()
on an arbitrary path string, because pathlib is OS-native --
pathlib.Path is PosixPath on this project's Linux development/test
environment, and PosixPath has no concept of a Windows drive letter.
Given a Windows-style string such as "C:/foo/bar.db", PosixPath
treats "C:" as an ordinary relative directory name and silently
produces the WRONG absolute path when resolved on a non-Windows
host (this was caught by test_database.py during Phase 1 and fixed
-- see that test file's comments). The fix: filesystem resolution
(which must use the *host's own* native pathlib, since it has to
match whatever OS this process is actually running on) is done once,
in create_readonly_engine(), using plain pathlib.Path(). The URI
STRING CONSTRUCTION is then a separate, pure, OS-independent step
(regex-based Windows-drive-letter detection on the string itself),
which is what makes it possible to unit-test both the POSIX and the
Windows code path from a single-OS test environment.
"""
from __future__ import annotations

import pathlib
import re
import sqlite3
from urllib.parse import quote

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

from .exceptions import DatabaseConfigError

#: Milliseconds SQLite will wait for a lock held by another
#: connection before raising SQLITE_BUSY. 30s is generous relative to
#: this project's expected single-digit-millisecond writes, and
#: matches the sqlite3-level `timeout` (seconds) passed to connect().
_BUSY_TIMEOUT_MS = 30_000
_CONNECT_TIMEOUT_S = 30

#: Matches a Windows absolute path with a drive letter, e.g.
#: "C:\foo\bar.db" or "C:/foo/bar.db". Deliberately a plain string
#: regex (not pathlib) so detection does not depend on which OS this
#: process is running on.
_WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")


def _to_sqlite_readonly_uri(absolute_path: str) -> str:
    """Build a sqlite3 URI (for use with sqlite3.connect(uri=True))
    that opens `absolute_path` strictly read-only via SQLite's
    mode=ro query parameter.

    `absolute_path` must already be an absolute path string, in its
    native OS separator style (backslash or forward slash). This
    function performs pure string manipulation only -- it never
    touches the filesystem and never goes through pathlib's
    OS-native Path classes -- which is what makes it possible to
    unit-test both the POSIX and the Windows path shape from a
    single-OS test environment (see tests/test_database.py).

    Per SQLite's URI filename documentation
    (https://www.sqlite.org/uri.html), a Windows drive-letter path
    must be given as "file:/C:/a/b/c.db" (one leading slash before
    the drive letter), not "file:C:/a/b/c.db".
    """
    normalized = absolute_path.replace("\\", "/")
    if _WINDOWS_DRIVE_PATTERN.match(absolute_path):
        normalized = "/" + normalized
    # Percent-encode characters (notably spaces) that are not safe
    # unescaped in a URI, while leaving the path separators and the
    # drive-letter colon intact.
    encoded = quote(normalized, safe="/:")
    return f"file:{encoded}?mode=ro"


def _apply_connection_pragmas(engine: Engine, *, read_only: bool) -> None:
    """Register a `connect` event that applies the required PRAGMAs
    to EVERY new DBAPI connection the engine's pool creates -- not
    just the first one. This is required because PRAGMA foreign_keys
    and PRAGMA busy_timeout are per-connection settings in SQLite,
    not persistent database settings (unlike journal_mode=WAL)."""

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        if read_only:
            # Defence in depth only: the authoritative read-only
            # enforcement is mode=ro on the connection URI below,
            # which SQLite's VFS layer enforces at the OS/file level
            # and which cannot be bypassed from SQL. query_only=ON
            # additionally produces a clearer SQLite-level error
            # message for a write attempt, before it would otherwise
            # be rejected by the VFS layer.
            cursor.execute("PRAGMA query_only = ON")
        cursor.close()


def create_write_engine(db_path: str) -> Engine:
    """Full read/write engine. Intended for exclusive use by this
    project's own agent code (shared/audit.py in a later phase)."""

    def _creator() -> sqlite3.Connection:
        return sqlite3.connect(db_path, timeout=_CONNECT_TIMEOUT_S)

    engine = create_engine("sqlite://", creator=_creator, future=True)
    _apply_connection_pragmas(engine, read_only=False)
    return engine


def create_readonly_engine(db_path: str) -> Engine:
    """Strictly read-only engine, for M4b's evaluation harness and
    M5's UI. Raises DatabaseConfigError if the database file does not
    already exist (a read-only connection cannot create one, and a
    missing file should fail loudly here rather than surfacing as a
    confusing SQLite error deeper in a query call).

    Filesystem resolution of a possibly-relative `db_path` uses the
    host's own native pathlib (correct for whatever OS this process
    is actually running on); the resulting absolute path string is
    then handed to _to_sqlite_readonly_uri() for pure string-based
    URI construction.
    """

    resolved = pathlib.Path(db_path).resolve()
    if not resolved.exists():
        raise DatabaseConfigError(
            f"cannot open a read-only engine: database file does not "
            f"exist: {resolved}"
        )

    uri = _to_sqlite_readonly_uri(str(resolved))

    def _creator() -> sqlite3.Connection:
        return sqlite3.connect(uri, uri=True, timeout=_CONNECT_TIMEOUT_S)

    engine = create_engine("sqlite://", creator=_creator, future=True)
    _apply_connection_pragmas(engine, read_only=True)
    return engine


def create_memory_engine() -> Engine:
    """In-memory database shared across all connections drawn from
    this engine's pool, for use by the test suite only."""

    def _creator() -> sqlite3.Connection:
        return sqlite3.connect(":memory:", timeout=_CONNECT_TIMEOUT_S, check_same_thread=False)

    engine = create_engine(
        "sqlite://",
        creator=_creator,
        poolclass=StaticPool,
        future=True,
    )
    _apply_connection_pragmas(engine, read_only=False)
    return engine
