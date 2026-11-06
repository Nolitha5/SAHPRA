"""Knowledge-base coverage report (the dashboard's Coverage tab).

Answers three questions from stored metadata only (never passage text):
* Which sources are indexed, with how many passages and pages?
* Which expected sources (from the sources manifest) are missing?
* For each CTD 3.2.S heading, how many passages would a filtered search see?
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app.schemas import ctd_ancestors

# Module 3.2.S headings an assessor works through.
S_SECTIONS: tuple[tuple[str, str], ...] = (
    ("3.2.S.1", "General information"),
    ("3.2.S.2", "Manufacture"),
    ("3.2.S.3", "Characterisation (incl. impurities)"),
    ("3.2.S.4", "Control of drug substance"),
    ("3.2.S.4.1", "Specification"),
    ("3.2.S.4.2", "Analytical procedures"),
    ("3.2.S.4.3", "Validation of analytical procedures"),
    ("3.2.S.4.4", "Batch analyses"),
    ("3.2.S.4.5", "Justification of specification"),
    ("3.2.S.5", "Reference standards or materials"),
    ("3.2.S.6", "Container closure system"),
    ("3.2.S.7", "Stability"),
)


def _source_key(org: Any, identifier: Any, version: Any) -> tuple[str, str, str]:
    return (str(org or "").strip().lower(), str(identifier or "").strip().lower(), str(version or "").strip().lower())


def load_expected_sources(manifest_path: Path) -> list[dict[str, Any]]:
    """Read the sources manifest; a missing or unreadable file means 'no expectations'."""
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [d for d in data if isinstance(d, dict) and d.get("source_identifier")] if isinstance(data, list) else []


def _section_counts(tag_counts: Mapping[str, int], section: str) -> tuple[int, int]:
    """(direct, reachable): passages tagged with the section or a subsection, and
    that plus passages tagged with a parent heading (what a filtered search sees)."""
    direct = sum(n for tag, n in tag_counts.items() if tag == section or tag.startswith(section + "."))
    parents = set(ctd_ancestors(section))
    inherited = sum(n for tag, n in tag_counts.items() if tag in parents)
    return direct, direct + inherited


def build_coverage(metadatas: Iterable[Mapping[str, Any]], expected: list[dict[str, Any]]) -> dict[str, Any]:
    rows = list(metadatas)
    sources: dict[tuple[str, str, str], dict[str, Any]] = {}
    pages: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    sections_per_source: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    tag_counts: Counter = Counter()
    incomplete = 0

    for m in rows:
        key = _source_key(m.get("issuing_organization"), m.get("source_identifier"), m.get("document_version"))
        if key not in sources:
            sources[key] = {
                "issuing_organization": m.get("issuing_organization"),
                "source_identifier": m.get("source_identifier"),
                "source_title": m.get("source_title"),
                "document_version": m.get("document_version"),
                "publication_date": m.get("publication_date"),
                "applicability_status": m.get("applicability_status"),
                "document_type": m.get("document_type"),
                "passages": 0,
            }
        sources[key]["passages"] += 1
        if isinstance(m.get("page_number"), int):
            pages[key].add(m["page_number"])
        tag = m.get("ctd_section")
        if tag:
            tag_counts[tag] += 1
            sections_per_source[key][tag] += 1
        if m.get("provenance_complete") is False:
            incomplete += 1

    expected_keys = {
        _source_key(e.get("issuing_organization"), e.get("source_identifier"), e.get("document_version")): e
        for e in expected
    }
    indexed = []
    for key, s in sources.items():
        p = sorted(pages[key])
        s.update(
            pages=len(p),
            first_page=p[0] if p else None,
            last_page=p[-1] if p else None,
            ctd_sections=dict(sorted(sections_per_source[key].items())),
            in_manifest=key in expected_keys,
            url=(expected_keys.get(key) or {}).get("url"),
        )
        indexed.append(s)
    indexed.sort(key=lambda s: (str(s["issuing_organization"]), str(s["source_identifier"])))

    missing = [
        {
            "issuing_organization": e.get("issuing_organization"),
            "source_identifier": e.get("source_identifier"),
            "source_title": e.get("source_title"),
            "document_version": e.get("document_version"),
            "url": e.get("url"),
        }
        for key, e in expected_keys.items()
        if key not in sources
    ]

    sections = []
    for code, label in S_SECTIONS:
        direct, reachable = _section_counts(tag_counts, code)
        sections.append({"section": code, "label": label, "direct": direct, "reachable": reachable})

    return {
        "total_passages": len(rows),
        "source_count": len(indexed),
        "expected_count": len(expected_keys),
        "incomplete_provenance": incomplete,
        "sources": indexed,
        "missing_sources": missing,
        "ctd_tags": dict(sorted(tag_counts.items())),
        "s_sections": sections,
    }
