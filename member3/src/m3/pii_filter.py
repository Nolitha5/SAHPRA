"""
Lightweight PII / confidentiality filter.

This is a regex-based first pass (emails, phone numbers, SA ID numbers,
potential patient identifiers) that runs with zero extra dependencies.
It is intentionally conservative and meant to be swapped for / combined
with Presidio (per the M3 tool list) once that dependency is approved for
the team's environment — the call signature below won't need to change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{3,4}\b")
# SA ID number: 13 digits, YYMMDD SSSS C A Z
_SA_ID_RE = re.compile(r"\b\d{6}\s?\d{4}\s?\d{2}\d\b")


@dataclass
class PiiScanResult:
    redacted_text: str
    hits: list[str] = field(default_factory=list)

    @property
    def contains_pii(self) -> bool:
        return bool(self.hits)


def scan_and_redact(text: str) -> PiiScanResult:
    hits: list[str] = []

    def _redact(pattern: re.Pattern, label: str, s: str) -> str:
        def _sub(m: re.Match) -> str:
            hits.append(label)
            return f"[REDACTED_{label}]"

        return pattern.sub(_sub, s)

    out = text
    out = _redact(_EMAIL_RE, "EMAIL", out)
    out = _redact(_SA_ID_RE, "SA_ID", out)
    out = _redact(_PHONE_RE, "PHONE", out)
    return PiiScanResult(redacted_text=out, hits=hits)
