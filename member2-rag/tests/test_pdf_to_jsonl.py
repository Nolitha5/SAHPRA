"""Temporary PDF converter: page numbers, chunking, headers, placeholders, validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import pdf_to_jsonl as conv

from app.knowledge_base.indexing import load_jsonl


def make_pdf(path: Path, pages: list[str]) -> Path:
    """Build a small text PDF with a running header and footer on every page."""
    canvas_mod = pytest.importorskip("reportlab.pdfgen.canvas")
    c = canvas_mod.Canvas(str(path))
    for n, body in enumerate(pages, start=1):
        c.drawString(72, 800, "TEST GUIDELINE HEADER")
        y = 760
        for line in body.splitlines():
            c.drawString(72, y, line)
            y -= 14
        c.drawString(72, 40, f"Page {n} of {len(pages)}")
        c.showPage()
    c.save()
    return path


def test_chunk_words_overlap():
    words = " ".join(f"w{i}" for i in range(10))
    chunks = conv.chunk_words(words, size=4, overlap=1)
    assert chunks[0] == "w0 w1 w2 w3" and chunks[1].startswith("w3")
    assert chunks[-1].endswith("w9")
    assert conv.chunk_words("", 4, 1) == []


def test_repair_split_words_joins_fragments_only():
    counts = conv.word_counts(["should should should defined defined defined tests tests tests",
                               "can not can not can not cannot in to in to into"])
    assert conv.repair_split_words("It shou ld be de fine d.", counts) == "It should be defined."
    assert conv.repair_split_words("All test s (shou ld), done", counts) == "All tests (should), done"

    assert conv.repair_split_words("we can not go in to it", counts) == "we can not go in to it"

    assert conv.repair_split_words("pseudo polymorphs", counts) == "pseudo polymorphs"


def test_clean_text_maps_symbol_font_and_hyphens():
    assert conv.clean_text(" Batch identity\n Limit  0.10 %") == "• Batch identity • Limit ≤ 0.10 %"
    assert conv.clean_text("specifi- \n  cation") == "specification"


def test_parse_page_sections():
    m = conv.parse_page_sections("1-2:3.2.s.4, 4:3.2.S.4.3")
    assert m == {1: "3.2.S.4", 2: "3.2.S.4", 4: "3.2.S.4.3"}
    with pytest.raises(ValueError):
        conv.parse_page_sections("5-2:3.2.S")
    with pytest.raises(ValueError):
        conv.parse_page_sections("1-2:not-a-section")


def test_placeholders_rejected(tmp_path):
    doc = conv.SourceDoc(pdf=tmp_path / "x.pdf", source_title="T", issuing_organization="ICH",
                         source_identifier="ICH QX", document_version="FILL IN from cover page")
    with pytest.raises(ValueError, match="placeholder"):
        conv.check_no_placeholder(doc)


def test_convert_pdf_end_to_end(tmp_path):
    def body(n):
        return "\n".join([f"Section {n} intro."] + ["Validation covers specificity accuracy precision."] * 6
                         + [f"Section {n} end."])
    pdf = make_pdf(tmp_path / "guide.pdf", [body(1), body(2), "", body(4)])
    doc = conv.SourceDoc(pdf=pdf, source_title="Test Guideline", issuing_organization="ICH",
                         source_identifier="ICH QTEST", document_version="1", publication_date="2020-01",
                         applicability_status="current", ctd_section="3.2.S.4",
                         page_sections={4: "3.2.S.4.3"})
    rows, report = conv.convert(doc, chunk_size=20, overlap=5)
    assert report.pages_total == 4 and report.pages_without_text == [3]
    assert report.header_footer_lines_removed >= 6
    assert all("HEADER" not in r["text"] and "Page" not in r["text"] for r in rows)
    assert all("Validation covers specificity" in r["text"] for r in rows if r["chunk_index"] == 0)
    assert {r["page_number"] for r in rows} == {1, 2, 4}
    assert {r["ctd_section"] for r in rows if r["page_number"] == 4} == {"3.2.S.4.3"}
    assert rows[0]["chunk_id"] == "ich-qtest-1-p1-c0-w20"

    out = tmp_path / "out.jsonl"
    out.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    loaded = load_jsonl(out)
    assert not loaded.errors and len(loaded.records) == len(rows)


def test_main_with_manifest(tmp_path, capsys):
    pdf = make_pdf(tmp_path / "a.pdf", [f"Page {i} topic.\nSpecification tests and acceptance criteria.\nEnd {i}."
                                        for i in "ABC"])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{
        "pdf": "a.pdf", "source_title": "A", "issuing_organization": "ICH",
        "source_identifier": "ICH QA", "document_version": "2", "applicability_status": "current",
        "ctd_section": "3.2.S.4.1"}]))
    out = tmp_path / "out.jsonl"
    assert conv.main(["--manifest", str(manifest), "--output", str(out), "--chunk-size", "50", "--overlap", "10"]) == 0
    assert len(out.read_text().splitlines()) == 3
    assert pdf.exists()

    manifest.write_text(json.dumps([{"pdf": "a.pdf", "source_title": "A", "issuing_organization": "ICH",
                                     "source_identifier": "ICH QA", "document_version": "FILL IN"}]))
    assert conv.main(["--manifest", str(manifest), "--output", str(out)]) == 1
