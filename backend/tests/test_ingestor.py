"""
tests/test_ingestor.py — Phase 2: Document Ingestion Service Tests
==================================================================

Tests T-ING-01 through T-ING-10 as specified in the Phase 2 proposal.

No confidential applicant data is used.  All tests use:
  - Small synthetic byte strings or in-memory DOCX files
  - Verbatim text from the already-read scratchpad (not the original files)

Regulatory note: these tests exercise ingestor.py logic only.
They do not upload real dossier documents.
"""

import io
import struct
import sys
import os

import pytest
from fastapi.testclient import TestClient

# Allow import of backend modules from the parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Minimal synthetic DOCX builder (no python-docx dependency for the builder)
# We use python-docx to BUILD test docs, which is acceptable since it is
# a test dependency and listed in requirements.txt.


def _make_docx_with_table(rows: list[list[str]]) -> bytes:
    """
    Build a minimal in-memory DOCX with one table and return its bytes.
    rows[0] is treated as the header row.
    """
    from docx import Document
    doc = Document()
    if not rows:
        return _doc_to_bytes(doc)
    table = doc.add_table(rows=len(rows), cols=len(rows[0]))
    for r_idx, row_data in enumerate(rows):
        for c_idx, cell_text in enumerate(row_data):
            table.rows[r_idx].cells[c_idx].text = cell_text
    return _doc_to_bytes(doc)


def _make_docx_with_headings(sections: list[tuple[str, str]]) -> bytes:
    """
    Build a minimal DOCX with alternating Heading 1 + paragraph pairs.
    sections = [(heading_text, body_text), ...]
    """
    from docx import Document
    doc = Document()
    for heading, body in sections:
        doc.add_heading(heading, level=1)
        doc.add_paragraph(body)
    return _doc_to_bytes(doc)


def _doc_to_bytes(doc) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── Minimal synthetic PDF (valid enough to pass magic-byte check) ─────────────
_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
    b"xref\n0 4\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF\n"
)


# ── Module under test ─────────────────────────────────────────────────────────
import ingestor
from ingestor import (
    validate_upload,
    compute_doc_id,
    ingest_document,
    list_documents,
    get_extractions,
    _DOC_STORE,
    _EXTRACTION_STORE,
)
from models import DocumentSourceType


@pytest.fixture(autouse=True)
def clear_stores():
    """Reset in-memory stores before every test to ensure isolation."""
    _DOC_STORE.clear()
    _EXTRACTION_STORE.clear()
    yield
    _DOC_STORE.clear()
    _EXTRACTION_STORE.clear()


# ─────────────────────────────────────────────────────────────────────────────
# T-ING-01: validate_upload rejects unsupported extension
# ─────────────────────────────────────────────────────────────────────────────
def test_ting_01_validate_rejects_unsupported_extension():
    """T-ING-01: .exe extension must raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        validate_upload("malware.exe", b"MZ\x90\x00")


# ─────────────────────────────────────────────────────────────────────────────
# T-ING-02: validate_upload rejects file over 20 MB
# ─────────────────────────────────────────────────────────────────────────────
def test_ting_02_validate_rejects_oversized_file():
    """T-ING-02: file > 20 MB must raise ValueError."""
    big = b"%PDF" + b"x" * (20 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="exceeds the 20 MB limit"):
        validate_upload("big.pdf", big)


# ─────────────────────────────────────────────────────────────────────────────
# T-ING-03: validate_upload rejects magic-byte mismatch
# ─────────────────────────────────────────────────────────────────────────────
def test_ting_03_validate_rejects_magic_byte_mismatch():
    """T-ING-03: PDF magic bytes in a .docx file must raise ValueError."""
    pdf_bytes_with_docx_ext = b"%PDF-1.4 some content"
    with pytest.raises(ValueError, match="ZIP/OOXML magic bytes"):
        validate_upload("disguised.docx", pdf_bytes_with_docx_ext)


# ─────────────────────────────────────────────────────────────────────────────
# T-ING-04: compute_doc_id returns consistent SHA-256
# ─────────────────────────────────────────────────────────────────────────────
def test_ting_04_compute_doc_id_consistent():
    """T-ING-04: same bytes must always produce the same SHA-256 hex string."""
    data = b"some regulatory content"
    id1 = compute_doc_id(data)
    id2 = compute_doc_id(data)
    assert id1 == id2
    assert len(id1) == 64        # SHA-256 hex = 64 chars
    assert id1 != compute_doc_id(data + b"x")


# ─────────────────────────────────────────────────────────────────────────────
# T-ING-05: extract_docx on a synthetic mapping table returns correct sections
# ─────────────────────────────────────────────────────────────────────────────
def test_ting_05_extract_docx_mapping_table():
    """
    T-ING-05: extract_docx on a 3-row mapping table (+ header) returns
    3 ExtractionResult objects with section_id matching the ID column.
    """
    rows = [
        ["ID", "IPRP group", "Requirement summary", "Data to extract"],
        ["S5-QAR-01", "QAR information", "Description and source", "API; standard name"],
        ["S5-QAR-02", "QAR information", "Primary standard", "Primary name; lot"],
        ["S5-AS-05", "Assessment point", "Sources used in testing", "Map each test"],
    ]
    docx_bytes = _make_docx_with_table(rows)
    doc_id = compute_doc_id(docx_bytes)

    from ingestor import extract_docx
    record, results = extract_docx(
        docx_bytes, "v2_mapping.docx", DocumentSourceType.V2_MAPPING, doc_id
    )

    assert len(results) == 3, f"Expected 3 rows, got {len(results)}: {[r.section_id for r in results]}"
    assert results[0].section_id == "S5-QAR-01"
    assert results[1].section_id == "S5-QAR-02"
    assert results[2].section_id == "S5-AS-05"
    for r in results:
        assert r.source_type == DocumentSourceType.V2_MAPPING
        assert r.doc_id == doc_id


# ─────────────────────────────────────────────────────────────────────────────
# T-ING-06: ingest_document stores record and returns correct section_count
# ─────────────────────────────────────────────────────────────────────────────
def test_ting_06_ingest_document_stores_and_returns():
    """
    T-ING-06: ingest_document stores the record in _DOC_STORE and returns
    correct section_count.
    """
    rows = [
        ["ID", "IPRP group", "Requirement summary"],
        ["S5-QAR-01", "QAR information", "Description and source"],
        ["S5-QAR-02", "QAR information", "Primary standard"],
    ]
    docx_bytes = _make_docx_with_table(rows)

    record, results = ingest_document(
        docx_bytes, "test_mapping.docx", DocumentSourceType.V2_MAPPING
    )

    assert record.doc_id in _DOC_STORE
    assert record.section_count == len(results)
    assert record.section_count == 2
    assert record.filename == "test_mapping.docx"
    assert record.source_type == DocumentSourceType.V2_MAPPING
    assert record.extraction_method == "python-docx"


# ─────────────────────────────────────────────────────────────────────────────
# T-ING-07: re-ingesting same bytes returns existing record (idempotent)
# ─────────────────────────────────────────────────────────────────────────────
def test_ting_07_reingest_same_bytes_is_idempotent():
    """
    T-ING-07: ingest_document called twice with the same bytes returns the
    existing record without duplicating entries.
    """
    rows = [
        ["ID", "IPRP group", "Requirement summary"],
        ["S5-QAR-01", "QAR information", "Description"],
    ]
    docx_bytes = _make_docx_with_table(rows)

    record1, results1 = ingest_document(
        docx_bytes, "test.docx", DocumentSourceType.V2_MAPPING
    )
    record2, results2 = ingest_document(
        docx_bytes, "test.docx", DocumentSourceType.V2_MAPPING
    )

    assert record1.doc_id == record2.doc_id
    assert len(_DOC_STORE) == 1       # only one entry stored


# ─────────────────────────────────────────────────────────────────────────────
# T-ING-08: GET /documents returns the ingested record
# ─────────────────────────────────────────────────────────────────────────────
def test_ting_08_list_documents_returns_record():
    """T-ING-08: list_documents() returns the DocumentRecord after ingestion."""
    rows = [
        ["ID", "IPRP group", "Requirement summary"],
        ["S5-AS-05", "Assessment point", "Sources used"],
    ]
    docx_bytes = _make_docx_with_table(rows)
    record, _ = ingest_document(docx_bytes, "test.docx", DocumentSourceType.V2_MAPPING)

    docs = list_documents()
    assert len(docs) == 1
    assert docs[0].doc_id == record.doc_id
    assert docs[0].source_type == DocumentSourceType.V2_MAPPING


# ─────────────────────────────────────────────────────────────────────────────
# T-ING-09: get_extractions returns the extracted sections
# ─────────────────────────────────────────────────────────────────────────────
def test_ting_09_get_extractions_returns_sections():
    """T-ING-09: get_extractions(doc_id) returns the list of ExtractionResult."""
    rows = [
        ["ID", "IPRP group", "Requirement summary"],
        ["S5-QAR-01", "QAR information", "Description"],
        ["S5-QAR-04", "QAR information", "Secondary standard"],
    ]
    docx_bytes = _make_docx_with_table(rows)
    record, _ = ingest_document(docx_bytes, "test.docx", DocumentSourceType.V2_MAPPING)

    sections = get_extractions(record.doc_id)
    assert sections is not None
    assert len(sections) == 2
    ids = {s.section_id for s in sections}
    assert "S5-QAR-01" in ids
    assert "S5-QAR-04" in ids


# ─────────────────────────────────────────────────────────────────────────────
# T-ING-10: get_extractions returns None for unknown doc_id
# ─────────────────────────────────────────────────────────────────────────────
def test_ting_10_get_extractions_unknown_id_returns_none():
    """T-ING-10: get_extractions with unknown doc_id returns None (→ HTTP 404)."""
    result = get_extractions("0" * 64)
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Bonus: HTTP endpoint integration tests via TestClient
# ─────────────────────────────────────────────────────────────────────────────
def test_endpoint_upload_and_list():
    """
    Bonus: POST /documents/upload → GET /documents round-trip via TestClient.
    Uses a minimal valid DOCX in memory; no real dossier files.
    """
    from unittest.mock import patch
    import ssl

    with patch.object(ssl.SSLContext, "load_verify_locations", return_value=None):
        from main import app
        client = TestClient(app)

    rows = [
        ["ID", "IPRP group", "Requirement summary"],
        ["S5-QAR-01", "QAR information", "Description and source"],
    ]
    docx_bytes = _make_docx_with_table(rows)

    resp = client.post(
        "/documents/upload",
        files={"file": ("mapping.docx", io.BytesIO(docx_bytes),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"source_type": "v2_mapping"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "doc_id" in body
    assert body["section_count"] == 1

    list_resp = client.get("/documents")
    assert list_resp.status_code == 200
    docs = list_resp.json()
    assert len(docs) == 1
    assert docs[0]["doc_id"] == body["doc_id"]

    ext_resp = client.get(f"/documents/{body['doc_id']}/extractions")
    assert ext_resp.status_code == 200
    exts = ext_resp.json()
    assert len(exts) == 1
    assert exts[0]["section_id"] == "S5-QAR-01"

    missing_resp = client.get("/documents/nonexistent" + "0" * 60 + "/extractions")
    assert missing_resp.status_code == 404


def test_endpoint_upload_duplicate_returns_409():
    """
    Bonus: uploading the same DOCX twice returns HTTP 409 on the second call.
    """
    from unittest.mock import patch
    import ssl

    with patch.object(ssl.SSLContext, "load_verify_locations", return_value=None):
        from main import app
        client = TestClient(app)

    rows = [
        ["ID", "IPRP group", "Requirement summary"],
        ["S5-QAR-02", "QAR information", "Primary standard"],
    ]
    docx_bytes = _make_docx_with_table(rows)

    r1 = client.post(
        "/documents/upload",
        files={"file": ("dup.docx", io.BytesIO(docx_bytes),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"source_type": "v2_mapping"},
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/documents/upload",
        files={"file": ("dup.docx", io.BytesIO(docx_bytes),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"source_type": "v2_mapping"},
    )
    assert r2.status_code == 409
    assert "already ingested" in r2.json()["detail"]["message"]


def test_endpoint_upload_invalid_source_type_returns_422():
    """
    Bonus: an unknown source_type returns HTTP 422.
    """
    from unittest.mock import patch
    import ssl

    with patch.object(ssl.SSLContext, "load_verify_locations", return_value=None):
        from main import app
        client = TestClient(app)

    rows = [["ID", "IPRP group"], ["S5-QAR-01", "QAR"]]
    docx_bytes = _make_docx_with_table(rows)

    resp = client.post(
        "/documents/upload",
        files={"file": ("f.docx", io.BytesIO(docx_bytes),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"source_type": "INVALID_TYPE"},
    )
    assert resp.status_code == 422
