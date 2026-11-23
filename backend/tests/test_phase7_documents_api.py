"""
tests/test_phase7_documents_api.py — Phase 7: Document Ingestion API Tests
===========================================================================

Tests T-DOC-01 through T-DOC-10.

Coverage
--------
T-DOC-01  GET  /documents                       empty store → 200, []
T-DOC-02  POST /documents/upload                valid DOCX + source_type → 200, doc_id + section_count
T-DOC-03  GET  /documents                       after upload → 200, list length 1
T-DOC-04  GET  /documents/{doc_id}/extractions  valid doc_id → 200, non-empty, raw_text present
T-DOC-05  GET  /documents/{doc_id}/extractions  unknown doc_id → 404
T-DOC-06  POST /documents/upload                duplicate file → 409 with existing doc_id
T-DOC-07  POST /documents/upload                invalid source_type → 422
T-DOC-08  POST /documents/upload                non-DOCX bytes → 422
T-DOC-09  POST /documents/upload                all five source_type values accepted
T-DOC-10  GET  /documents/{doc_id}/extractions  source_type preserved on each ExtractionResult

Must be run on the device (python -m pytest tests/test_phase7_documents_api.py)
because main.py imports adapters.m1_adapter and adapters.m4_adapter.

No confidential applicant data is used.
"""

import io
import sys
import os

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from main import app
import ingestor
from ingestor import _DOC_STORE, _EXTRACTION_STORE

client = TestClient(app)


# ---------------------------------------------------------------------------
# Shared synthetic DOCX builder
# ---------------------------------------------------------------------------

def _make_docx(sections: list[tuple[str, str]]) -> bytes:
    """Build a minimal in-memory DOCX from (heading, body) pairs."""
    from docx import Document
    doc = Document()
    for heading, body in sections:
        doc.add_heading(heading, level=1)
        doc.add_paragraph(body)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Autouse fixture — clear stores before and after every test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_stores():
    _DOC_STORE.clear()
    _EXTRACTION_STORE.clear()
    yield
    _DOC_STORE.clear()
    _EXTRACTION_STORE.clear()


# ---------------------------------------------------------------------------
# T-DOC-01: GET /documents — empty store → 200, empty list
# ---------------------------------------------------------------------------

def test_tdoc_01_list_documents_empty():
    """T-DOC-01: no documents uploaded → GET /documents returns empty list."""
    response = client.get("/documents")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert response.json() == [], f"Expected [], got {response.json()!r}"


# ---------------------------------------------------------------------------
# T-DOC-02: POST /documents/upload — valid DOCX → 200 with doc_id + section_count
# ---------------------------------------------------------------------------

def test_tdoc_02_upload_valid_docx_returns_doc_id():
    """T-DOC-02: valid DOCX + valid source_type → 200, doc_id present, section_count >= 1."""
    docx_bytes = _make_docx([
        ("S.5 Reference Standards", "USP Aspirin reference standard — lot R09060, USP 47."),
    ])
    response = client.post(
        "/documents/upload",
        files={"file": ("aspirin_ref.docx", docx_bytes,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"source_type": "iprp_guidance"},
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()
    assert "doc_id" in body, f"Expected doc_id in response, got {body!r}"
    assert body["filename"] == "aspirin_ref.docx"
    assert body["source_type"] == "iprp_guidance"
    assert isinstance(body["doc_id"], str) and len(body["doc_id"]) == 64, (
        f"doc_id should be a 64-char SHA-256 hex string, got {body['doc_id']!r}"
    )
    assert body["section_count"] >= 1, (
        f"Expected at least 1 extracted section, got {body['section_count']}"
    )


# ---------------------------------------------------------------------------
# T-DOC-03: GET /documents — after upload → list of 1
# ---------------------------------------------------------------------------

def test_tdoc_03_list_documents_after_upload():
    """T-DOC-03: after one upload, GET /documents returns a list of length 1."""
    docx_bytes = _make_docx([
        ("Reference Standards", "BP Paracetamol reference standard — BP 2024."),
    ])
    upload_resp = client.post(
        "/documents/upload",
        files={"file": ("para_ref.docx", docx_bytes,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"source_type": "pharmacopoeia"},
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["doc_id"]

    list_resp = client.get("/documents")
    assert list_resp.status_code == 200
    docs = list_resp.json()
    assert len(docs) == 1, f"Expected 1 document, got {len(docs)}"
    assert docs[0]["doc_id"] == doc_id, (
        f"doc_id mismatch: {docs[0]['doc_id']!r} != {doc_id!r}"
    )


# ---------------------------------------------------------------------------
# T-DOC-04: GET /documents/{doc_id}/extractions — valid doc_id → non-empty list
# ---------------------------------------------------------------------------

def test_tdoc_04_get_extractions_valid_doc_id():
    """T-DOC-04: valid doc_id → 200, non-empty list, each item has raw_text."""
    docx_bytes = _make_docx([
        ("S.5 Reference Standards", "USP Ibuprofen reference standard — lot R12345, USP 47."),
    ])
    upload_resp = client.post(
        "/documents/upload",
        files={"file": ("ibup_ref.docx", docx_bytes,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"source_type": "iprp_guidance"},
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["doc_id"]

    ext_resp = client.get(f"/documents/{doc_id}/extractions")
    assert ext_resp.status_code == 200, f"Expected 200, got {ext_resp.status_code}: {ext_resp.text}"
    extractions = ext_resp.json()
    assert len(extractions) >= 1, f"Expected at least 1 extraction, got {len(extractions)}"
    for item in extractions:
        assert "raw_text" in item, f"ExtractionResult missing raw_text: {item!r}"
        assert item["raw_text"], "raw_text must not be empty"


# ---------------------------------------------------------------------------
# T-DOC-05: GET /documents/{doc_id}/extractions — unknown doc_id → 404
# ---------------------------------------------------------------------------

def test_tdoc_05_get_extractions_unknown_doc_id_returns_404():
    """T-DOC-05: unknown doc_id → 404."""
    fake_id = "a" * 64
    response = client.get(f"/documents/{fake_id}/extractions")
    assert response.status_code == 404, (
        f"Expected 404 for unknown doc_id, got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# T-DOC-06: POST /documents/upload — duplicate file → 409
# ---------------------------------------------------------------------------

def test_tdoc_06_upload_duplicate_file_returns_409():
    """T-DOC-06: uploading the same file twice → 409 with existing doc_id."""
    docx_bytes = _make_docx([
        ("S.5 Standards", "Ph.Eur. Caffeine reference standard — Ph.Eur. 11.0."),
    ])
    file_tuple = ("caffeine_ref.docx", docx_bytes,
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    first = client.post(
        "/documents/upload",
        files={"file": file_tuple},
        data={"source_type": "pharmacopoeia"},
    )
    assert first.status_code == 200
    doc_id = first.json()["doc_id"]

    # Re-upload the identical bytes
    second = client.post(
        "/documents/upload",
        files={"file": ("caffeine_ref.docx", docx_bytes,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"source_type": "pharmacopoeia"},
    )
    assert second.status_code == 409, (
        f"Expected 409 for duplicate upload, got {second.status_code}: {second.text}"
    )
    detail = second.json().get("detail", {})
    # The existing doc_id must appear in the error detail
    assert doc_id in str(detail), (
        f"Expected existing doc_id {doc_id!r} in 409 detail, got {detail!r}"
    )


# ---------------------------------------------------------------------------
# T-DOC-07: POST /documents/upload — invalid source_type → 422
# ---------------------------------------------------------------------------

def test_tdoc_07_upload_invalid_source_type_returns_422():
    """T-DOC-07: unrecognised source_type → 422."""
    docx_bytes = _make_docx([("Standards", "Some text.")])
    response = client.post(
        "/documents/upload",
        files={"file": ("test.docx", docx_bytes,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"source_type": "not_a_valid_source_type"},
    )
    assert response.status_code == 422, (
        f"Expected 422 for invalid source_type, got {response.status_code}"
    )


# ---------------------------------------------------------------------------
# T-DOC-08: POST /documents/upload — non-DOCX bytes → 422
# ---------------------------------------------------------------------------

def test_tdoc_08_upload_non_docx_bytes_returns_422():
    """T-DOC-08: plain-text bytes sent as DOCX → 422 (magic bytes check fails)."""
    fake_bytes = b"This is not a DOCX file at all."
    response = client.post(
        "/documents/upload",
        files={"file": ("notadocx.docx", fake_bytes,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"source_type": "iprp_guidance"},
    )
    assert response.status_code == 422, (
        f"Expected 422 for non-DOCX bytes, got {response.status_code}: {response.text}"
    )


# ---------------------------------------------------------------------------
# T-DOC-09: POST /documents/upload — all five source_type values accepted
# ---------------------------------------------------------------------------

def test_tdoc_09_all_source_types_accepted():
    """T-DOC-09: each of the five valid source_type values returns 200."""
    source_types = ["iprp_guidance", "pharmacopoeia", "v2_mapping", "score_report", "other"]
    for st in source_types:
        # Distinct content per upload to avoid duplicate-rejection
        docx_bytes = _make_docx([
            ("Section", f"Test document for source_type={st}. USP Aspirin reference."),
        ])
        response = client.post(
            "/documents/upload",
            files={"file": (f"test_{st}.docx", docx_bytes,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"source_type": st},
        )
        assert response.status_code == 200, (
            f"Expected 200 for source_type={st!r}, got {response.status_code}: {response.text}"
        )
        assert "doc_id" in response.json(), (
            f"doc_id missing in response for source_type={st!r}"
        )


# ---------------------------------------------------------------------------
# T-DOC-10: source_type preserved on each ExtractionResult
# ---------------------------------------------------------------------------

def test_tdoc_10_source_type_preserved_on_extractions():
    """T-DOC-10: source_type on each ExtractionResult matches the uploaded value."""
    source_type = "score_report"
    docx_bytes = _make_docx([
        ("Pilot Report", "SCoRE pilot assessment: USP Aspirin reference standard lot R09060."),
    ])
    upload_resp = client.post(
        "/documents/upload",
        files={"file": ("score.docx", docx_bytes,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        data={"source_type": source_type},
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["doc_id"]

    ext_resp = client.get(f"/documents/{doc_id}/extractions")
    assert ext_resp.status_code == 200
    extractions = ext_resp.json()
    assert len(extractions) >= 1
    for item in extractions:
        assert item["source_type"] == source_type, (
            f"Expected source_type={source_type!r}, got {item['source_type']!r}"
        )




def test_applicant_dossier_upload_is_rejected():
    response = client.post(
        "/documents/upload",
        files={"file": ("dossier.docx", _make_docx([("3.2.S.5", "Synthetic example")]))},
        data={"source_type": "applicant_dossier"},
    )

    assert response.status_code == 422
    assert _DOC_STORE == {}
