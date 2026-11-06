"""Tests for Phase 2 Knowledge Base Integration (v1.3).

Covers:
- Source inventory CSV integrity
- Copy manifest hash verification
- Quarantine enforcement (HTML files never approved)
- ChromaDB/BGE index presence checks (non-blocking if index not built)
- Dossier chunk metadata constraints
- Source classification rules
"""
from __future__ import annotations
import csv, json
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
INVENTORY_CSV = PROJECT / "regulatory_sources" / "PHARMACY_SOURCE_INVENTORY.csv"
COPY_MANIFEST = PROJECT / "pharmacopoeia" / "incoming" / "COPY_MANIFEST.json"
RAW_FROM_PHARMACY = PROJECT / "pharmacopoeia" / "incoming" / "raw_from_pharmacy"
QUARANTINE = PROJECT / "pharmacopoeia" / "quarantine"
REGULATORY_CHROMA_REPORT = PROJECT / "local_indexes" / "regulatory_chroma" / "ACTUAL_CHROMA_RUN.json"
DOSSIER_CHROMA_REPORT = PROJECT / "local_indexes" / "dossier_chroma" / "DOSSIER_CHROMA_RUN.json"


# ---------------------------------------------------------------------------
# Source inventory tests
# ---------------------------------------------------------------------------

class TestPharmacySourceInventory:
    def test_csv_exists(self):
        assert INVENTORY_CSV.exists(), f"Missing: {INVENTORY_CSV}"

    def test_csv_row_count(self):
        rows = list(csv.DictReader(INVENTORY_CSV.open(encoding="utf-8")))
        assert len(rows) >= 45, f"Expected ≥45 rows, got {len(rows)}"

    def test_all_rows_have_sha256(self):
        rows = list(csv.DictReader(INVENTORY_CSV.open(encoding="utf-8")))
        missing = [r["filename"] for r in rows if not r.get("sha256")]
        assert not missing, f"Missing SHA-256: {missing}"

    def test_sha256_format(self):
        rows = list(csv.DictReader(INVENTORY_CSV.open(encoding="utf-8")))
        for r in rows:
            sha = r.get("sha256", "")
            assert len(sha) == 64 and all(c in "0123456789abcdef" for c in sha), \
                f"Invalid SHA-256 for {r['filename']}: {sha!r}"

    def test_category_values_are_valid(self):
        valid = {"A_REGULATORY_GUIDANCE", "B_REVIEWED_PHARMA",
                 "C_DRAFT_PHARM_RESEARCH", "D_SPONSOR_DOSSIER"}
        rows = list(csv.DictReader(INVENTORY_CSV.open(encoding="utf-8")))
        invalid = [r["filename"] for r in rows if r.get("category") not in valid]
        assert not invalid, f"Invalid category values: {invalid}"

    def test_html_files_are_class_c(self):
        rows = list(csv.DictReader(INVENTORY_CSV.open(encoding="utf-8")))
        html_rows = [r for r in rows if r.get("extension") == ".html"]
        wrong_cat = [r["filename"] for r in html_rows
                     if r.get("category") != "C_DRAFT_PHARM_RESEARCH"]
        assert not wrong_cat, f"HTML files not Class C: {wrong_cat}"

    def test_three_substances_covered(self):
        rows = list(csv.DictReader(INVENTORY_CSV.open(encoding="utf-8")))
        substances = {r.get("substance") for r in rows}
        for expected in ("valsartan", "amlodipine", "hydrochlorothiazide"):
            assert expected in substances, f"Substance not found in inventory: {expected}"

    def test_html_publisher_flagged_unofficial(self):
        rows = list(csv.DictReader(INVENTORY_CSV.open(encoding="utf-8")))
        html_rows = [r for r in rows if r.get("extension") == ".html"]
        for r in html_rows:
            assert "UNOFFICIAL" in r.get("publisher", "") or "webofpharma" in r.get("publisher", ""), \
                f"HTML file not flagged as unofficial: {r['filename']}"


# ---------------------------------------------------------------------------
# Copy manifest tests
# ---------------------------------------------------------------------------

class TestCopyManifest:
    def test_manifest_exists(self):
        assert COPY_MANIFEST.exists(), f"Missing: {COPY_MANIFEST}"

    def test_all_copies_verified(self):
        manifest = json.loads(COPY_MANIFEST.read_text(encoding="utf-8"))
        failures = [c for c in manifest.get("copies", [])
                    if "FAILED" in c.get("status", "")]
        assert not failures, f"Copy failures: {[c['source'] for c in failures]}"

    def test_45_pdfs_in_manifest(self):
        manifest = json.loads(COPY_MANIFEST.read_text(encoding="utf-8"))
        assert len(manifest.get("copies", [])) >= 45, \
            f"Expected ≥45 PDF copies, got {len(manifest.get('copies', []))}"

    def test_5_html_quarantined(self):
        manifest = json.loads(COPY_MANIFEST.read_text(encoding="utf-8"))
        assert len(manifest.get("html_quarantine", [])) == 5, \
            f"Expected 5 HTML quarantine entries"

    def test_html_quarantine_approved_false(self):
        manifest = json.loads(COPY_MANIFEST.read_text(encoding="utf-8"))
        for item in manifest.get("html_quarantine", []):
            assert item.get("approved") is False, \
                f"HTML quarantine item incorrectly approved: {item.get('source')}"
            assert item.get("provenance_verified") is False, \
                f"HTML quarantine item has provenance_verified=True: {item.get('source')}"


# ---------------------------------------------------------------------------
# Quarantine directory tests
# ---------------------------------------------------------------------------

class TestQuarantineDirectory:
    def test_quarantine_dir_exists(self):
        assert QUARANTINE.exists()

    def test_quarantine_has_5_html_files(self):
        html_files = list(QUARANTINE.glob("*.html"))
        assert len(html_files) == 5, f"Expected 5 HTML files, found {len(html_files)}"

    def test_quarantine_substance_coverage(self):
        html_files = [f.name.lower() for f in QUARANTINE.glob("*.html")]
        content = " ".join(html_files)
        for substance in ("valsartan", "amlodipine", "hydrochlorothiazide"):
            assert substance in content, \
                f"No {substance} HTML file found in quarantine: {html_files}"

    def test_no_pdfs_in_quarantine(self):
        pdf_files = list(QUARANTINE.glob("*.pdf"))
        assert not pdf_files, f"PDFs should not be in quarantine: {pdf_files}"


# ---------------------------------------------------------------------------
# Raw copy directory tests
# ---------------------------------------------------------------------------

class TestRawFromPharmacyDirectory:
    def test_substance_subdirs_exist(self):
        for substance in ("valsartan", "amlodipine", "hydrochlorothiazide"):
            d = RAW_FROM_PHARMACY / substance
            assert d.exists(), f"Missing subdirectory: {d}"

    def test_valsartan_pdf_count(self):
        pdfs = list((RAW_FROM_PHARMACY / "valsartan").glob("*.pdf"))
        assert len(pdfs) == 14, f"Expected 14 Valsartan PDFs, got {len(pdfs)}"

    def test_amlodipine_pdf_count(self):
        pdfs = list((RAW_FROM_PHARMACY / "amlodipine").glob("*.pdf"))
        assert len(pdfs) == 16, f"Expected 16 Amlodipine PDFs, got {len(pdfs)}"

    def test_hctz_pdf_count(self):
        pdfs = list((RAW_FROM_PHARMACY / "hydrochlorothiazide").glob("*.pdf"))
        assert len(pdfs) == 15, f"Expected 15 HCTZ PDFs, got {len(pdfs)}"

    def test_no_non_pdf_files_in_raw(self):
        for subdir in RAW_FROM_PHARMACY.iterdir():
            if not subdir.is_dir():
                continue
            non_pdf = [f for f in subdir.iterdir()
                       if f.is_file() and f.suffix.lower() != ".pdf"]
            assert not non_pdf, f"Non-PDF files in {subdir.name}: {[f.name for f in non_pdf]}"


# ---------------------------------------------------------------------------
# ChromaDB reports (non-blocking — skip if index not yet built)
# ---------------------------------------------------------------------------

class TestRegulatoryChromaReport:
    def test_report_exists_or_skip(self):
        if not REGULATORY_CHROMA_REPORT.exists():
            pytest.skip("Regulatory ChromaDB index not yet built")

    def test_backend_is_actual_chromadb(self):
        if not REGULATORY_CHROMA_REPORT.exists():
            pytest.skip("Regulatory ChromaDB index not yet built")
        report = json.loads(REGULATORY_CHROMA_REPORT.read_text(encoding="utf-8"))
        assert report["backend"] == "ACTUAL_CHROMADB", \
            f"Backend must be ACTUAL_CHROMADB, got {report['backend']!r}"

    def test_chunk_count_matches_corpus(self):
        if not REGULATORY_CHROMA_REPORT.exists():
            pytest.skip("Regulatory ChromaDB index not yet built")
        report = json.loads(REGULATORY_CHROMA_REPORT.read_text(encoding="utf-8"))
        assert report["chunk_count"] >= 500, \
            f"Expected ≥500 chunks, got {report['chunk_count']}"

    def test_vector_dimension_is_1024(self):
        if not REGULATORY_CHROMA_REPORT.exists():
            pytest.skip("Regulatory ChromaDB index not yet built")
        report = json.loads(REGULATORY_CHROMA_REPORT.read_text(encoding="utf-8"))
        assert report["vector_dimension"] == 1024, \
            f"Expected 1024-dim BGE vectors, got {report['vector_dimension']}"

    def test_regulatory_source_approval_false(self):
        if not REGULATORY_CHROMA_REPORT.exists():
            pytest.skip("Regulatory ChromaDB index not yet built")
        report = json.loads(REGULATORY_CHROMA_REPORT.read_text(encoding="utf-8"))
        assert report.get("regulatory_source_approval") is False


class TestDossierChromaReport:
    def test_report_exists_or_skip(self):
        if not DOSSIER_CHROMA_REPORT.exists():
            pytest.skip("Dossier ChromaDB index not yet built")

    def test_backend_is_actual_chromadb(self):
        if not DOSSIER_CHROMA_REPORT.exists():
            pytest.skip("Dossier ChromaDB index not yet built")
        report = json.loads(DOSSIER_CHROMA_REPORT.read_text(encoding="utf-8"))
        assert report["backend"] == "ACTUAL_CHROMADB"

    def test_classification_is_sponsor_dossier(self):
        if not DOSSIER_CHROMA_REPORT.exists():
            pytest.skip("Dossier ChromaDB index not yet built")
        report = json.loads(DOSSIER_CHROMA_REPORT.read_text(encoding="utf-8"))
        assert report["classification"] == "D_SPONSOR_DOSSIER"

    def test_requires_human_review(self):
        if not DOSSIER_CHROMA_REPORT.exists():
            pytest.skip("Dossier ChromaDB index not yet built")
        report = json.loads(DOSSIER_CHROMA_REPORT.read_text(encoding="utf-8"))
        assert report.get("requires_human_review") is True

    def test_regulatory_source_approval_false(self):
        if not DOSSIER_CHROMA_REPORT.exists():
            pytest.skip("Dossier ChromaDB index not yet built")
        report = json.loads(DOSSIER_CHROMA_REPORT.read_text(encoding="utf-8"))
        assert report.get("regulatory_source_approval") is False

    def test_smoke_test_results_present(self):
        if not DOSSIER_CHROMA_REPORT.exists():
            pytest.skip("Dossier ChromaDB index not yet built")
        report = json.loads(DOSSIER_CHROMA_REPORT.read_text(encoding="utf-8"))
        smoke = report.get("smoke_tests", [])
        assert len(smoke) >= 3, "Expected ≥3 smoke test queries"
        for s in smoke:
            assert s["hits"] > 0, f"Smoke query returned 0 hits: {s['query']}"
