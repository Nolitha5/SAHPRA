"""
Shared exception hierarchy for the Container Closure Agent S6 project.

All modules in this project raise exceptions from this hierarchy rather
than letting raw SQLAlchemy / sqlite3 / Pydantic exceptions propagate
unwrapped, so calling code (agents, tests, future M4b/M5 integration)
has a single, stable set of exception types to catch.
"""
from __future__ import annotations


class S6BaseError(Exception):
    """Root of the project's exception hierarchy."""


class DatabaseConfigError(S6BaseError):
    """Raised when the database cannot be configured or opened as
    requested (e.g. a read-only engine requested against a database
    file that does not yet exist)."""


class AuditError(S6BaseError):
    """Root of audit-subsystem errors."""


class AuditWriteError(AuditError):
    """Raised when a write to the events/findings/decisions tables
    fails (constraint violation, lock timeout, etc.). Writing
    functions always roll back the transaction before raising this."""


class AuditQueryError(AuditError):
    """Raised when a read-only query against the audit tables fails."""


class AdapterError(S6BaseError):
    """Root of integration-adapter errors (M1/M2/M3/M4b). Raised by
    stub or real adapters when an upstream dependency is unavailable
    or returns data that cannot be parsed into our contracts."""
