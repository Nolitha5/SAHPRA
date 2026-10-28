"""Structured logging with protection against leaking confidential content.

Rules followed across the code base:
* Never log passage text, sponsor evidence content or full user questions.
* Log identifiers, counts, timings and a short hash of a question instead.

`safe_fingerprint()` gives a stable, non-reversible tag for a piece of text so
log lines can be correlated without exposing the text itself.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_CONFIGURED = False


_FORBIDDEN_KEYS = {"text", "content", "sponsor_content", "passage_text", "question", "query"}


def safe_fingerprint(text: str | None) -> str:
    """Return a short SHA-256 fingerprint (12 hex chars) of `text`."""
    if not text:
        return "empty"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(redact(extra))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def redact(fields: dict[str, Any]) -> dict[str, Any]:
    """Replace forbidden keys with a fingerprint so content is never logged."""
    clean: dict[str, Any] = {}
    for key, value in fields.items():
        if key in _FORBIDDEN_KEYS:
            clean[f"{key}_fingerprint"] = safe_fingerprint(str(value))
        else:
            clean[key] = value
    return clean


def configure_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Configure the root `member2` logger once per process."""
    global _CONFIGURED
    logger = logging.getLogger("member2")
    logger.setLevel(level)
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stderr)
    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the `member2` namespace."""
    return logging.getLogger(f"member2.{name}")


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Log an event with structured, redacted fields."""
    logger.log(level, event, extra={"fields": redact(fields)})
