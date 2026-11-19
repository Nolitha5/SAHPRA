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
from datetime import date

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+27[ -]?\d{2}[ -]?\d{3}[ -]?\d{4}"
    r"|(?:\(0\d{2}\)|0\d{2})[ -]\d{3}[ -]\d{4})(?!\w)"
)
_LABELLED_PHONE_RE = re.compile(
    r"(\b(?:phone|tel(?:ephone)?|mobile|cell(?:phone)?|fax)\s*(?:no\.?|number)?\s*[:=]?\s*)"
    r"(\+?\d(?:[() -]*\d){6,14})(?!\w)", re.I,
)
# SA ID number: 13 digits, YYMMDD SSSS C A Z
_SA_ID_RE = re.compile(r"\b\d{6}[ -]?\d{4}[ -]?\d{3}\b")
_ID_LABEL_RE = re.compile(
    r"\b(?:ID|identity)(?:\s+(?:no\.?|number))?\s*[:=]?\s*$", re.I,
)
_PERSON_FIELD_RE = re.compile(
    r"(?im)^(\s*(?:patient name|patient ID|patient identifier|date of birth|DOB|"
    r"personal address|home address|passport(?: number)?)\s*[:=][ \t]*)([^\r\n]+)"
)


def _valid_sa_id(value: str) -> bool:
    digits = [int(char) for char in value if char.isascii() and char.isdigit()]
    if len(digits) != 13 or digits[10] not in (0, 1):
        return False
    try:
        date(2000 + int("".join(map(str, digits[:2]))),
             10 * digits[2] + digits[3], 10 * digits[4] + digits[5])
    except ValueError:
        return False
    return sum(
        digit if i % 2 == 0 else (digit * 2 - 9 if digit >= 5 else digit * 2)
        for i, digit in enumerate(digits)
    ) % 10 == 0


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

    def redact_id(match: re.Match) -> str:
        preceding = match.string[max(0, match.start() - 64):match.start()]
        if _valid_sa_id(match[0]) or _ID_LABEL_RE.search(preceding):
            hits.append("SA_ID")
            return "[REDACTED_SA_ID]"
        return match[0]

    def labelled_replacement(match: re.Match, label: str) -> str:
        hits.append(label)
        return f"{match[1]}[REDACTED_{label}]"

    out = _SA_ID_RE.sub(redact_id, text)
    out = _PERSON_FIELD_RE.sub(lambda m: labelled_replacement(m, "PERSONAL_FIELD"), out)
    out = _redact(_EMAIL_RE, "EMAIL", out)
    out = _LABELLED_PHONE_RE.sub(lambda m: labelled_replacement(m, "PHONE"), out)
    out = _redact(_PHONE_RE, "PHONE", out)
    return PiiScanResult(redacted_text=out, hits=hits)
