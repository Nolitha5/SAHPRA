"""
CTD section recognition for Module 3.2.S (Drug Substance).

Golden rule for this layer (from the M3 personal spec): preserve the CTD
section on everything, and never let a garbled or empty extraction pass
silently — flag it instead.

This module is pure stdlib (regex + simple state machine) so it can be
unit-tested without any heavy dependencies, and reused unchanged whichever
PDF backend (Docling / PyMuPDF / Unstructured) produced the raw lines.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Canonical S.1 .. S.7 headings per the IPRP QWGG guidance / ICH M4Q structure.
_KNOWN_SECTIONS = {
    "S.1": "General Information",
    "S.1.1": "Nomenclature",
    "S.1.2": "Structure",
    "S.1.3": "General Properties",
    "S.2": "Manufacture",
    "S.2.1": "Manufacturer(s)",
    "S.2.2": "Description of Manufacturing Process and Process Controls",
    "S.2.3": "Control of Materials",
    "S.2.4": "Controls of Critical Steps and Intermediates",
    "S.2.5": "Process Validation and/or Evaluation",
    "S.2.6": "Manufacturing Process Development",
    "S.3": "Characterisation",
    "S.3.1": "Elucidation of Structure and other Characteristics",
    "S.3.2": "Impurities",
    "S.4": "Control of the Drug Substance",
    "S.4.1": "Specification",
    "S.4.2": "Analytical Procedures",
    "S.4.3": "Validation of Analytical Procedures",
    "S.4.4": "Batch Analyses",
    "S.4.5": "Justification of Specification",
    "S.5": "Reference Standards or Materials",
    "S.6": "Container Closure System",
    "S.7": "Stability",
    "S.7.1": "Stability Summary and Conclusions",
    "S.7.2": "Post-approval Stability Protocol and Stability Commitment",
    "S.7.3": "Stability Data",
}

# Matches "3.2.S.4.1", "3.2.S.4", "S.4.1", "S.4" — with optional trailing
# heading text — at the start of a line (allowing leading numbering noise).
_HEADING_RE = re.compile(
    r"^\s*(?:3\.2\.)?(S(?:\.\d+){1,3})\b[\s:.\-]*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SectionMatch:
    code: str  # canonical "3.2.S.x.y"
    short_code: str  # "S.x.y"
    title: str | None
    confidence: float  # 1.0 = exact known heading, 0.6 = recognised pattern only


def detect_heading(line: str) -> SectionMatch | None:
    """Return a SectionMatch if `line` looks like a CTD S.x[.y[.z]] heading."""
    stripped = line.strip()
    if not stripped:
        return None
    m = _HEADING_RE.match(stripped)
    if not m:
        return None
    short = m.group(1).upper()
    # Normalise "S.04.1" style accidental zero-padding, keep digits as-is otherwise.
    parts = short.split(".")
    short = ".".join([parts[0]] + [str(int(p)) for p in parts[1:]])
    title = stripped[m.end():].strip(" -:.") or _KNOWN_SECTIONS.get(short)
    confidence = 1.0 if short in _KNOWN_SECTIONS else 0.6
    return SectionMatch(
        code=f"3.2.{short}",
        short_code=short,
        title=title,
        confidence=confidence,
    )


class SectionTracker:
    """Walks lines/pages in order, tracking the current CTD section.

    Usage:
        tracker = SectionTracker()
        for line in lines:
            tracker.feed(line)
            section = tracker.current  # "3.2.S.4.1" or None before first heading
    """

    def __init__(self) -> None:
        self.current: str | None = None
        self.current_confidence: float = 0.0

    def feed(self, line: str) -> SectionMatch | None:
        match = detect_heading(line)
        if match is not None:
            self.current = match.code
            self.current_confidence = match.confidence
        return match
