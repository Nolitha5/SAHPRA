"""Tables from the source PDFs: extraction, storage, and how the API shows them."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.knowledge_base.pdf_tables import TableStore, extract_tables, write_tables_file
from tests.test_api import _client


def make_pdf_with_table(path: Path) -> Path:
    """A one-page PDF: a paragraph, a ruled 3x3 table, and a one-row box that is not a table."""
    platypus = pytest.importorskip("reportlab.platypus")
    colors = pytest.importorskip("reportlab.lib.colors")
    styles = pytest.importorskip("reportlab.lib.styles").getSampleStyleSheet()
    grid = [("GRID", (0, 0), (-1, -1), 0.8, colors.black)]
    story = [
        platypus.Paragraph("Impurities above these thresholds should be reported and identified.",
                           styles["Normal"]),
        platypus.Spacer(1, 12),
        platypus.Table([["Maximum Daily Dose", "Reporting Threshold", "Identification Threshold"],
                        ["≤ 2g/day", "0.05%", "0.10%"], ["> 2g/day", "0.03%", "0.05%"]], style=grid),
        platypus.Spacer(1, 24),
        platypus.Table([["Note: one boxed line only"]], style=grid),
    ]
    platypus.SimpleDocTemplate(str(path)).build(story)
    return path


def test_extracts_the_table_with_its_values_and_an_image(tmp_path):
    pdf = make_pdf_with_table(tmp_path / "guide.pdf")
    tables = extract_tables(pdf, "ich-qtest-1", "ICH QTEST", "1", ["7"], 1, None, tmp_path / "img")
    assert len(tables) == 1  # the one-row box is not kept
    t = tables[0]
    assert t["rows"] == [["Maximum Daily Dose", "Reporting Threshold", "Identification Threshold"],
                         ["≤ 2g/day", "0.05%", "0.10%"], ["> 2g/day", "0.03%", "0.05%"]]
    assert (t["table_id"], t["page_number"], t["page_label"]) == ("ich-qtest-1-p1-t1", 1, "7")
    image = tmp_path / "img" / t["image"]
    assert image.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and t["width"] > 0 and t["height"] > 0


def test_footnote_markers_stay_superscript_and_never_join_the_number(tmp_path):
    platypus = pytest.importorskip("reportlab.platypus")
    colors = pytest.importorskip("reportlab.lib.colors")
    styles = pytest.importorskip("reportlab.lib.styles").getSampleStyleSheet()
    cell = platypus.Paragraph("0.12<super>1)</super>", styles["Normal"])
    table = platypus.Table([["Raw result", "Reported result"], ["0.12", cell], ["0.044", "Not reported"]],
                           style=[("GRID", (0, 0), (-1, -1), 0.8, colors.black)])
    platypus.SimpleDocTemplate(str(tmp_path / "fn.pdf")).build([table])
    rows = extract_tables(tmp_path / "fn.pdf", "x", "X", "1", [None], 1, None, tmp_path / "img")[0]["rows"]
    assert rows[1][1] == "0.12¹⁾"  # not "0.121)"


def _store(tmp_path: Path, tables: list[dict]) -> TableStore:
    images = tmp_path / "tables"
    images.mkdir()
    for t in tables:
        (images / t["image"]).write_bytes(b"\x89PNG\r\n\x1a\n")
    write_tables_file(tmp_path / "processed" / "t.json", images, tables)
    return TableStore(tmp_path / "processed" / "t.json")


def _table(table_id="synth-gl-a-1-0-p2-t1", page=2):
    return {"table_id": table_id, "source_identifier": "SYNTH-GL-A", "document_version": "1.0", "page_number": page,
            "page_label": None, "index_on_page": 1, "rows": [["Test", "Limit"], ["Assay", "98.0-102.0%"]],
            "image": f"{table_id}.png", "width": 400, "height": 120}


def test_store_finds_tables_by_page_and_never_builds_paths_from_input(tmp_path):
    store = _store(tmp_path, [_table()])
    assert [t["table_id"] for t in store.for_page("SYNTH-GL-A", "1.0", 2)] == ["synth-gl-a-1-0-p2-t1"]
    assert store.for_page("SYNTH-GL-A", "1.0", 3) == [] and store.for_page("SYNTH-GL-A", "2.0", 2) == []
    assert store.image_path("synth-gl-a-1-0-p2-t1").name == "synth-gl-a-1-0-p2-t1.png"
    assert store.image_path("unknown-table") is None
    assert store.image_path("../../.env") is None
    assert TableStore(tmp_path / "missing.json").for_page("SYNTH-GL-A", "1.0", 2) == []


def test_findings_carry_page_tables_and_images_are_served(settings, populated_store, embedder, tmp_path):
    _store(tmp_path, [_table()])
    client = _client(settings.with_overrides(tables_file=tmp_path / "processed" / "t.json"), populated_store, embedder,
                     tmp_path=tmp_path)
    findings = client.post("/api/agents/evidence-rera", json={
        "ctd_section": "3.2.S.4.3",
        "assessment_question": "validation of analytical procedures specificity accuracy"}).json()
    tables = findings[0]["page_tables"]["syn-val-1"]  # syn-val-1 is on page 2 of SYNTH-GL-A v1.0
    assert tables[0]["rows"][1] == ["Assay", "98.0-102.0%"]
    assert tables[0]["image_url"] == "/api/tables/synth-gl-a-1-0-p2-t1/image"

    image = client.get(tables[0]["image_url"])
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert client.get("/api/tables/no-such-table/image").status_code == 404
    assert client.get("/api/tables/..%2F..%2F.env/image").status_code == 404

    question = "validation of analytical procedures specificity accuracy"
    asked = client.post("/api/ask", json={"question": question}).json()
    assert "page_tables" in asked["findings"][0]
