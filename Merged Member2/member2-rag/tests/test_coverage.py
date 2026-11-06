"""Coverage report: indexed sources, missing sources and CTD section reach."""

from __future__ import annotations

import json

from app.knowledge_base.coverage import build_coverage, load_expected_sources
from tests.conftest import SYNTHETIC_CORPUS
from tests.test_api import _client


def _meta(identifier, section, page, version="1.0", org="TEST"):
    return {"issuing_organization": org, "source_identifier": identifier, "source_title": identifier,
            "document_version": version, "ctd_section": section, "page_number": page,
            "applicability_status": "current", "document_type": "guideline", "provenance_complete": True}


def test_counts_sources_pages_and_sections():
    metas = [_meta("A", "3.2.S.4.1", 1), _meta("A", "3.2.S.4.1", 1), _meta("A", "3.2.S.4.3", 5), _meta("B", "3.2", 2)]
    report = build_coverage(metas, [])
    a = next(s for s in report["sources"] if s["source_identifier"] == "A")
    assert (a["passages"], a["pages"], a["first_page"], a["last_page"]) == (3, 2, 1, 5)
    assert a["ctd_sections"] == {"3.2.S.4.1": 2, "3.2.S.4.3": 1}
    assert report["total_passages"] == 4 and report["source_count"] == 2


def test_section_reach_includes_parent_headings():
    metas = [_meta("A", "3.2.S.4.1", 1), _meta("B", "3.2", 1), _meta("C", "3.2.S", 1), _meta("D", "3.2.S.7", 1)]
    sections = {s["section"]: s for s in build_coverage(metas, [])["s_sections"]}
    # Direct: tagged with the section or a subsection. Reachable: + parent headings (3.2.S, 3.2).
    assert (sections["3.2.S.4"]["direct"], sections["3.2.S.4"]["reachable"]) == (1, 3)
    assert (sections["3.2.S.4.1"]["direct"], sections["3.2.S.4.1"]["reachable"]) == (1, 3)
    assert (sections["3.2.S.5"]["direct"], sections["3.2.S.5"]["reachable"]) == (0, 2)  # a gap


def test_missing_and_unlisted_sources(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([
        {"issuing_organization": "TEST", "source_identifier": "A", "document_version": "1.0", "url": "https://x/a.pdf"},
        {"issuing_organization": "TEST", "source_identifier": "Z", "document_version": "1.0"},
    ]), encoding="utf-8")
    report = build_coverage([_meta("A", "3.2.S", 1), _meta("B", "3.2.S", 1)], load_expected_sources(manifest))
    by_id = {s["source_identifier"]: s for s in report["sources"]}
    assert by_id["A"]["in_manifest"] and by_id["A"]["url"] == "https://x/a.pdf"
    assert not by_id["B"]["in_manifest"]
    assert [m["source_identifier"] for m in report["missing_sources"]] == ["Z"]


def test_unreadable_manifest_means_no_expectations(tmp_path):
    assert load_expected_sources(tmp_path / "absent.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert load_expected_sources(bad) == []


def test_coverage_endpoint(settings, populated_store, embedder, tmp_path):
    client = _client(settings.with_overrides(sources_manifest=tmp_path / "none.json"), populated_store, embedder,
                     tmp_path=tmp_path)
    body = client.get("/api/coverage").json()
    assert body["total_passages"] == len(SYNTHETIC_CORPUS)
    assert body["collection"] == settings.collection_name
    assert body["missing_sources"] == []
    assert all("text" not in s for s in body["sources"])  # metadata only, never passage text
