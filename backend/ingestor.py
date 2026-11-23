"""
backend/ingestor.py — Phase 2: Document Ingestion Service
==========================================================

Ingests regulatory source documents (PDF and DOCX) and stores extracted
sections in memory for later use by the retrieval and assessment layers.

Supported document types
------------------------
  IPRP_GUIDANCE  — IPRP QWGG Guidance PDF; extracts S.5 section (page 18).
  PHARMACOPOEIA  — Ph. Eur. 5.12 PDF; extracts all section paragraphs.
  V2_MAPPING     — M5 S.5 Requirement-to-Data Mapping DOCX; extracts table rows.
  SCORE_REPORT   — SCoRE pilot report DOCX; extracts S.5 blocks per API.

Regulatory guardrails
---------------------
  * raw_text is verbatim extracted content only.  Nothing is inferred or
    fabricated.
  * source_type is preserved on every ExtractionResult so that applicant
    evidence (SCORE_REPORT), regulatory guidance (IPRP_GUIDANCE /
    PHARMACOPOEIA) and internal specifications (V2_MAPPING) are never
    conflated during retrieval.
  * No verdict, qa_status or evidence_sufficiency logic lives here.
  * No file is written to disk; bytes are processed in memory only.
  * OCR is flagged but not performed in this prototype.

Change-control note
-------------------
  This file was added in Phase 2.  No existing files were modified except
  models.py (two new models appended) and main.py (three new endpoints
  appended).  s5_standards.py, qa_critic.py, retrieval.py and
  ollama_reviewer.py are untouched.
"""

from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime, timezone
from typing import Optional

from models import (
    DocumentRecord,
    DocumentSourceType,
    ExtractionResult,
)

# ── In-memory stores (prototype) ─────────────────────────────────────────────
# Pattern mirrors _MOCK_RECORDS in s5_standards.py.
# doc_id (SHA-256 hex) → DocumentRecord
_DOC_STORE: dict[str, DocumentRecord] = {}

# doc_id → list of ExtractionResult
_EXTRACTION_STORE: dict[str, list[ExtractionResult]] = {}

# ── Constants ─────────────────────────────────────────────────────────────────
_MAX_FILE_BYTES = 20 * 1024 * 1024          # 20 MB hard limit
_ALLOWED_EXTENSIONS = {".pdf", ".docx"}
_PDF_MAGIC = b"%PDF"
_DOCX_MAGIC = b"PK\x03\x04"               # ZIP/OOXML magic bytes


# ── Public API ────────────────────────────────────────────────────────────────

def validate_upload(filename: str, content_bytes: bytes) -> None:
    """
    Validate a file upload before any parsing begins.

    Checks:
      1. Extension is .pdf or .docx (case-insensitive).
      2. File size does not exceed _MAX_FILE_BYTES.
      3. Magic bytes match the declared extension.

    Raises ValueError with a descriptive message on any failure.
    Does not write to disk.
    """
    ext = _get_ext(filename)
    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type '{ext}'. "
            f"Only PDF (.pdf) and Word (.docx) documents are accepted."
        )

    if len(content_bytes) > _MAX_FILE_BYTES:
        mb = len(content_bytes) / (1024 * 1024)
        raise ValueError(
            f"File is {mb:.1f} MB, which exceeds the 20 MB limit."
        )

    if ext == ".pdf" and not content_bytes[:4] == _PDF_MAGIC:
        raise ValueError(
            "File has a .pdf extension but does not start with the PDF "
            "magic bytes (%PDF). The file may be corrupt or mislabelled."
        )

    if ext == ".docx" and content_bytes[:4] != _DOCX_MAGIC:
        raise ValueError(
            "File has a .docx extension but does not start with the "
            "expected ZIP/OOXML magic bytes. The file may be corrupt or "
            "mislabelled."
        )


def compute_doc_id(content_bytes: bytes) -> str:
    """
    Return the SHA-256 hex digest of the file bytes.

    Used as a stable, content-addressable document identifier.  Re-uploading
    the same file will produce the same doc_id, enabling deduplication.
    """
    return hashlib.sha256(content_bytes).hexdigest()


def ingest_document(
    content_bytes: bytes,
    filename: str,
    source_type: DocumentSourceType,
) -> tuple[DocumentRecord, list[ExtractionResult]]:
    """
    Full ingestion pipeline for one document.

    Steps:
      1. validate_upload — rejects invalid files before any parsing.
      2. compute_doc_id — deduplicates by content hash.
      3. Dispatch to extract_pdf or extract_docx.
      4. Store results in _DOC_STORE and _EXTRACTION_STORE.
      5. Return (DocumentRecord, list[ExtractionResult]).

    If the doc_id is already present in _DOC_STORE the existing record is
    returned unchanged (idempotent re-upload).  The caller may detect this
    condition and return HTTP 409.

    Does not write to disk.
    """
    validate_upload(filename, content_bytes)
    doc_id = compute_doc_id(content_bytes)

    if doc_id in _DOC_STORE:
        return _DOC_STORE[doc_id], _EXTRACTION_STORE.get(doc_id, [])

    ext = _get_ext(filename)
    if ext == ".pdf":
        record, results = extract_pdf(content_bytes, filename, source_type, doc_id)
    else:
        record, results = extract_docx(content_bytes, filename, source_type, doc_id)

    _DOC_STORE[doc_id] = record
    _EXTRACTION_STORE[doc_id] = results
    return record, results


def list_documents() -> list[DocumentRecord]:
    """Return all ingested DocumentRecord objects."""
    return list(_DOC_STORE.values())


def get_extractions(doc_id: str) -> Optional[list[ExtractionResult]]:
    """
    Return ExtractionResult list for a doc_id, or None if not found.
    Caller should return HTTP 404 when None is returned.
    """
    if doc_id not in _DOC_STORE:
        return None
    return _EXTRACTION_STORE.get(doc_id, [])


# ── PDF extraction ────────────────────────────────────────────────────────────

def extract_pdf(
    content_bytes: bytes,
    filename: str,
    source_type: DocumentSourceType,
    doc_id: str,
) -> tuple[DocumentRecord, list[ExtractionResult]]:
    """
    Extract text sections from a PDF.

    Strategy:
      1. Try pypdf.  If any page yields non-empty text, use it throughout.
      2. Fall back to pdfplumber for pages that pypdf returns empty.
      3. If both return empty for a page, mark extraction_confidence=LOW and
         add a warning (OCR would be needed but is out of scope).

    Section identification:
      IPRP_GUIDANCE  — scan for "S.5" / "reference standard" heading; treat
                       each identified page block as one section.
      PHARMACOPOEIA  — split on paragraph markers and numbered section headers.
      Others         — one ExtractionResult per page as a fallback.
    """
    warnings: list[str] = []
    page_texts: list[str] = []
    method_used = "pypdf"

    try:
        import pypdf  # noqa: PLC0415
        reader = pypdf.PdfReader(io.BytesIO(content_bytes))
        page_count = len(reader.pages)
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            page_texts.append(text)
        empty_pages = [i + 1 for i, t in enumerate(page_texts) if not t.strip()]
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"pypdf failed: {exc}; falling back to pdfplumber")
        page_texts = []
        empty_pages = []
        page_count = 0
        method_used = "pdfplumber"

    # Fall back to pdfplumber for pages pypdf left empty (or for all pages
    # if pypdf itself failed).
    if empty_pages or not page_texts:
        try:
            import pdfplumber  # noqa: PLC0415
            with pdfplumber.open(io.BytesIO(content_bytes)) as pdf:
                if not page_texts:
                    page_count = len(pdf.pages)
                    page_texts = [""] * page_count
                    method_used = "pdfplumber"
                for i in (range(page_count) if not page_texts else
                           [p - 1 for p in empty_pages]):
                    text = pdf.pages[i].extract_text() or ""
                    if text.strip():
                        page_texts[i] = text
                        if method_used == "pypdf":
                            method_used = "pypdf+pdfplumber"
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"pdfplumber also failed on some pages: {exc}")

    still_empty = [i + 1 for i, t in enumerate(page_texts) if not t.strip()]
    if still_empty:
        warnings.append(
            f"Pages with no extractable text (OCR may be needed): "
            f"{still_empty}"
        )

    # ── Build ExtractionResult list ──────────────────────────────────────────
    if source_type == DocumentSourceType.IPRP_GUIDANCE:
        results = _extract_iprp_sections(page_texts, doc_id, source_type, warnings)
    elif source_type == DocumentSourceType.PHARMACOPOEIA:
        results = _extract_pheur_sections(page_texts, doc_id, source_type, warnings)
    elif source_type == DocumentSourceType.APPLICANT_DOSSIER:
        results = _extract_applicant_s5_sections(
            page_texts, doc_id, source_type, warnings
        )
    else:
        results = _extract_pdf_pages_generic(
            page_texts, doc_id, source_type, warnings
        )

    record = DocumentRecord(
        doc_id=doc_id,
        filename=filename,
        source_type=source_type,
        page_count=page_count,
        section_count=len(results),
        ingested_at=_utcnow(),
        extraction_method=method_used,
        ocr_used=False,
        warnings=warnings,
    )
    return record, results


def _extract_iprp_sections(
    page_texts: list[str],
    doc_id: str,
    source_type: DocumentSourceType,
    warnings: list[str],
) -> list[ExtractionResult]:
    """
    Identify S.5 content in the IPRP PDF.

    Heuristic: scan each page for "S.5" or "reference standard" (case-
    insensitive).  Collect matched pages as sections.  Also emit one section
    per page that contains a QAR bullet marker ("Information to be stated").
    """
    results: list[ExtractionResult] = []
    s5_pattern = re.compile(
        r"(S\.5|reference\s+standard|reference\s+material)", re.IGNORECASE
    )
    qar_pattern = re.compile(
        r"(information\s+to\s+be\s+stated|points?\s+to\s+be\s+considered)",
        re.IGNORECASE,
    )

    for page_num, text in enumerate(page_texts, start=1):
        if not text.strip():
            continue
        confidence: str = "HIGH"
        section_id: Optional[str] = None
        section_title = f"IPRP page {page_num}"
        notes: list[str] = []

        if s5_pattern.search(text):
            section_id = f"iprp_s5_p{page_num}"
            section_title = f"IPRP S.5 Reference Standards — page {page_num}"
        elif qar_pattern.search(text):
            section_id = f"iprp_qar_p{page_num}"
            section_title = f"IPRP QAR section — page {page_num}"
        else:
            # Include all pages but mark lower confidence
            section_id = f"iprp_p{page_num}"
            confidence = "MEDIUM"
            notes.append("S.5 / QAR keywords not found on this page")

        results.append(ExtractionResult(
            doc_id=doc_id,
            section_id=section_id,
            section_title=section_title,
            page_or_line=f"p.{page_num}",
            raw_text=text,
            source_type=source_type,
            extraction_confidence=confidence,
            notes=notes,
        ))

    if not results:
        warnings.append("No pages with extractable text found in IPRP PDF")
    return results


def _extract_pheur_sections(
    page_texts: list[str],
    doc_id: str,
    source_type: DocumentSourceType,
    warnings: list[str],
) -> list[ExtractionResult]:
    """
    Extract sections from the Ph. Eur. 5.12 PDF.

    Splits each page on numbered section markers (e.g. "4-2-3", "4-5") and
    top-level headings.  One ExtractionResult per identified block.
    """
    results: list[ExtractionResult] = []
    section_header = re.compile(
        r"(?m)^(\d[\d\-]*\.?\s+[A-Z][A-Za-z\s]{3,})", re.MULTILINE
    )

    for page_num, text in enumerate(page_texts, start=1):
        if not text.strip():
            continue
        # Try to split on section headers within the page
        splits = section_header.split(text)
        if len(splits) > 1:
            # splits: [pre, header1, body1, header2, body2, ...]
            # Emit pre-header text as its own block if non-trivial
            if splits[0].strip():
                results.append(ExtractionResult(
                    doc_id=doc_id,
                    section_id=f"pheur_5_12_p{page_num}_intro",
                    section_title=f"Ph. Eur. 5.12 — page {page_num} intro",
                    page_or_line=f"p.{page_num}",
                    raw_text=splits[0].strip(),
                    source_type=source_type,
                    extraction_confidence="HIGH",
                ))
            i = 1
            while i < len(splits) - 1:
                header_text = splits[i].strip()
                body_text = splits[i + 1].strip() if i + 1 < len(splits) else ""
                slug = re.sub(r"[^a-z0-9]+", "_", header_text.lower())[:40]
                results.append(ExtractionResult(
                    doc_id=doc_id,
                    section_id=f"pheur_{slug}_p{page_num}",
                    section_title=f"Ph. Eur. 5.12 — {header_text}",
                    page_or_line=f"p.{page_num}",
                    raw_text=f"{header_text}\n{body_text}".strip(),
                    source_type=source_type,
                    extraction_confidence="HIGH",
                ))
                i += 2
        else:
            # No sub-headers found; emit whole page as one section
            results.append(ExtractionResult(
                doc_id=doc_id,
                section_id=f"pheur_5_12_p{page_num}",
                section_title=f"Ph. Eur. 5.12 — page {page_num}",
                page_or_line=f"p.{page_num}",
                raw_text=text,
                source_type=source_type,
                extraction_confidence="MEDIUM",
                notes=["No sub-section headers identified on this page"],
            ))

    if not results:
        warnings.append("No extractable text found in Ph. Eur. PDF")
    return results


def _extract_pdf_pages_generic(
    page_texts: list[str],
    doc_id: str,
    source_type: DocumentSourceType,
    warnings: list[str],
) -> list[ExtractionResult]:
    """Fallback: one ExtractionResult per page with extractable text."""
    results = []
    for page_num, text in enumerate(page_texts, start=1):
        if not text.strip():
            continue
        results.append(ExtractionResult(
            doc_id=doc_id,
            section_id=f"pdf_p{page_num}",
            section_title=f"Page {page_num}",
            page_or_line=f"p.{page_num}",
            raw_text=text,
            source_type=source_type,
            extraction_confidence="MEDIUM",
            notes=["Generic page extraction; no section structure identified"],
        ))
    return results


# ── DOCX extraction ───────────────────────────────────────────────────────────

def extract_docx(
    content_bytes: bytes,
    filename: str,
    source_type: DocumentSourceType,
    doc_id: str,
) -> tuple[DocumentRecord, list[ExtractionResult]]:
    """
    Extract text sections from a DOCX file.

    Dispatch by source_type:
      V2_MAPPING   — parse the IPRP mapping table rows (columns: ID, IPRP
                     group, Requirement summary, …).
      SCORE_REPORT — extract S.5 text blocks per API heading.
      Others       — extract all paragraphs grouped under heading styles.
    """
    warnings: list[str] = []

    try:
        from docx import Document as DocxDocument  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "python-docx is not installed.  "
            "Add 'python-docx>=1.1.2' to requirements.txt."
        ) from exc

    doc = DocxDocument(io.BytesIO(content_bytes))

    if source_type == DocumentSourceType.V2_MAPPING:
        results = _extract_v2_mapping_tables(doc, doc_id, source_type, warnings)
    elif source_type == DocumentSourceType.SCORE_REPORT:
        results = _extract_score_s5_sections(doc, doc_id, source_type, warnings)
    elif source_type == DocumentSourceType.APPLICANT_DOSSIER:
        # Convert DOCX paragraphs to page-like list for the shared extractor
        _docx_pages = [p.text for p in doc.paragraphs if p.text.strip()]
        results = _extract_applicant_s5_sections(
            _docx_pages, doc_id, source_type, warnings
        )
    else:
        results = _extract_docx_paragraphs_generic(
            doc, doc_id, source_type, warnings
        )

    record = DocumentRecord(
        doc_id=doc_id,
        filename=filename,
        source_type=source_type,
        page_count=None,                # DOCX has no fixed page boundaries
        section_count=len(results),
        ingested_at=_utcnow(),
        extraction_method="python-docx",
        ocr_used=False,
        warnings=warnings,
    )
    return record, results


def _extract_v2_mapping_tables(
    doc,
    doc_id: str,
    source_type: DocumentSourceType,
    warnings: list[str],
) -> list[ExtractionResult]:
    """
    Parse the IPRP requirement-to-data mapping table from the V2 DOCX.

    The mapping table has columns: ID | IPRP group | Requirement summary |
    Data to extract | Assessment question | Evidence to inspect | Guardrail |
    Reference.

    Strategy: scan all tables for one whose first row contains both "ID" and
    "IPRP group" (case-insensitive).  Extract each subsequent row as one
    ExtractionResult with section_id = row's ID cell value.
    """
    results: list[ExtractionResult] = []
    mapping_table = None
    id_col: Optional[int] = None
    group_col: Optional[int] = None
    req_col: Optional[int] = None

    for table in doc.tables:
        if not table.rows:
            continue
        header_cells = [c.text.strip().lower() for c in table.rows[0].cells]
        # Accept any table whose header row contains "id" and "iprp group"
        # (or just "iprp") as adjacent indicators
        if any("id" == h for h in header_cells) and any(
            "iprp" in h for h in header_cells
        ):
            mapping_table = table
            id_col = next(
                (i for i, h in enumerate(header_cells) if h == "id"), None
            )
            group_col = next(
                (i for i, h in enumerate(header_cells) if "iprp" in h), None
            )
            req_col = next(
                (
                    i
                    for i, h in enumerate(header_cells)
                    if "requirement" in h or "summary" in h
                ),
                None,
            )
            break

    if mapping_table is None:
        warnings.append(
            "V2 mapping table not found (expected columns: ID, IPRP group, "
            "Requirement summary).  Falling back to paragraph extraction."
        )
        return _extract_docx_paragraphs_generic(
            doc, doc_id, source_type, warnings
        )

    for row_num, row in enumerate(mapping_table.rows[1:], start=2):
        cells = row.cells
        if len(cells) == 0:
            continue
        # Build cell text safely
        cell_texts = [c.text.strip() for c in cells]
        section_id = cell_texts[id_col].strip() if id_col is not None else f"row_{row_num}"
        if not section_id:
            section_id = f"row_{row_num}"

        iprp_group = (
            cell_texts[group_col].strip()
            if group_col is not None and group_col < len(cell_texts)
            else ""
        )
        req_summary = (
            cell_texts[req_col].strip()
            if req_col is not None and req_col < len(cell_texts)
            else ""
        )
        # Combine all cell text as raw_text for completeness
        raw_text = " | ".join(cell_texts)

        results.append(ExtractionResult(
            doc_id=doc_id,
            section_id=section_id,
            section_title=(
                f"{iprp_group} — {req_summary[:60]}"
                if iprp_group or req_summary
                else f"Mapping row {row_num}"
            ),
            page_or_line=f"row {row_num}",
            raw_text=raw_text,
            source_type=source_type,
            extraction_confidence="HIGH",
        ))

    if not results:
        warnings.append("Mapping table was found but contained no data rows")
    return results


def _extract_score_s5_sections(
    doc,
    doc_id: str,
    source_type: DocumentSourceType,
    warnings: list[str],
) -> list[ExtractionResult]:
    """
    Extract S.5 blocks from the SCoRE pilot report DOCX.

    Strategy: iterate paragraphs; detect API-level headings (style Heading 1
    or Heading 2, or lines containing the API substance names); within each
    API block, detect "S.5" sub-headings; collect paragraph text until the
    next heading of equal or higher level.
    """
    results: list[ExtractionResult] = []
    paragraphs = doc.paragraphs

    # Identify heading levels by style name or heuristic (all-caps short line)
    current_api: Optional[str] = None
    in_s5_block = False
    s5_buffer: list[str] = []
    s5_start_line: Optional[int] = None
    line_num = 0

    s5_heading_re = re.compile(r"\bS\.5\b", re.IGNORECASE)
    next_section_re = re.compile(r"\bS\.\d\b", re.IGNORECASE)

    def flush_s5(api: str, start: int, lines: list[str]) -> None:
        if not lines:
            return
        slug = re.sub(r"[^a-z0-9]+", "_", api.lower())[:30]
        results.append(ExtractionResult(
            doc_id=doc_id,
            section_id=f"score_{slug}_s5",
            section_title=f"SCoRE S.5 — {api}",
            page_or_line=f"para {start}",
            raw_text="\n".join(lines).strip(),
            source_type=source_type,
            extraction_confidence="HIGH",
        ))

    for para in paragraphs:
        line_num += 1
        style_name = para.style.name.lower() if para.style else ""
        text = para.text.strip()
        if not text:
            continue

        is_heading = "heading" in style_name or (
            len(text) < 80 and text.isupper()
        )

        if is_heading and next_section_re.search(text) and not s5_heading_re.search(text):
            # Moving to a non-S.5 CTD section — flush any open S.5 block
            if in_s5_block and current_api:
                flush_s5(current_api, s5_start_line or line_num, s5_buffer)
                s5_buffer = []
                in_s5_block = False

        if is_heading and not s5_heading_re.search(text):
            # Potential API-level heading
            if in_s5_block and current_api:
                flush_s5(current_api, s5_start_line or line_num, s5_buffer)
                s5_buffer = []
                in_s5_block = False
            # Treat short headings as API identifiers
            if len(text) < 120:
                current_api = text
            continue

        if s5_heading_re.search(text):
            if in_s5_block and current_api:
                flush_s5(current_api, s5_start_line or line_num, s5_buffer)
                s5_buffer = []
            in_s5_block = True
            s5_start_line = line_num
            s5_buffer.append(text)
            continue

        if in_s5_block:
            s5_buffer.append(text)

    # Flush final block
    if in_s5_block and current_api and s5_buffer:
        flush_s5(current_api, s5_start_line or line_num, s5_buffer)

    if not results:
        warnings.append(
            "No S.5 blocks identified in SCoRE DOCX; "
            "falling back to full paragraph extraction"
        )
        return _extract_docx_paragraphs_generic(
            doc, doc_id, source_type, warnings
        )
    return results


def _extract_docx_paragraphs_generic(
    doc,
    doc_id: str,
    source_type: DocumentSourceType,
    warnings: list[str],
) -> list[ExtractionResult]:
    """
    Fallback: group all non-empty paragraphs under detected headings.
    One ExtractionResult per top-level heading block.
    """
    results: list[ExtractionResult] = []
    current_heading = "Document start"
    current_lines: list[str] = []
    block_start = 1

    for line_num, para in enumerate(doc.paragraphs, start=1):
        text = para.text.strip()
        if not text:
            continue
        style_name = para.style.name.lower() if para.style else ""
        is_heading = "heading" in style_name

        if is_heading:
            if current_lines:
                slug = re.sub(r"[^a-z0-9]+", "_", current_heading.lower())[:40]
                results.append(ExtractionResult(
                    doc_id=doc_id,
                    section_id=f"docx_{slug}_l{block_start}",
                    section_title=current_heading,
                    page_or_line=f"para {block_start}",
                    raw_text="\n".join(current_lines).strip(),
                    source_type=source_type,
                    extraction_confidence="MEDIUM",
                    notes=["Generic paragraph extraction"],
                ))
            current_heading = text
            current_lines = []
            block_start = line_num
        else:
            current_lines.append(text)

    # Flush final block
    if current_lines:
        slug = re.sub(r"[^a-z0-9]+", "_", current_heading.lower())[:40]
        results.append(ExtractionResult(
            doc_id=doc_id,
            section_id=f"docx_{slug}_l{block_start}",
            section_title=current_heading,
            page_or_line=f"para {block_start}",
            raw_text="\n".join(current_lines).strip(),
            source_type=source_type,
            extraction_confidence="MEDIUM",
            notes=["Generic paragraph extraction"],
        ))

    return results


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_ext(filename: str) -> str:
    """Return lower-case file extension including the dot, e.g. '.pdf'."""
    dot = filename.rfind(".")
    return filename[dot:].lower() if dot != -1 else ""


def _utcnow() -> str:
    """Return current UTC time as ISO 8601 string with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Phase 3 — Applicant dossier extraction  (additive; no existing code changed)
# ---------------------------------------------------------------------------

# CTD section heading patterns that signal 3.2.S.5 content
_S5_HEADING_RE = re.compile(
    r"3\.2\.S\.5|reference\s+standard|working\s+standard|primary\s+standard",
    re.IGNORECASE,
)

# Sub-section keywords mapped to canonical field names for structured output
_S5_SUBSECTION_MAP: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"primary\s+(reference\s+)?standard", re.IGNORECASE),  "primary_reference_standard"),
    (re.compile(r"working\s+standard",                 re.IGNORECASE),  "working_standard"),
    (re.compile(r"impurit",                            re.IGNORECASE),  "impurity_standards"),
    (re.compile(r"batch\s*(number|no\.?|num)",         re.IGNORECASE),  "batch_numbers"),
    (re.compile(r"purit|assay|content",                re.IGNORECASE),  "purity_assay"),
    (re.compile(r"certif",                             re.IGNORECASE),  "certificate_of_analysis"),
    (re.compile(r"expir|retest|valid",                 re.IGNORECASE),  "expiry_retest"),
    (re.compile(r"storage|condition",                  re.IGNORECASE),  "storage_conditions"),
]


def _extract_applicant_s5_sections(
    raw_text_pages: list[str],
    doc_id: str,
    source_type: "DocumentSourceType",
    warnings: list[str],
) -> list["ExtractionResult"]:
    """
    Extract CTD 3.2.S.5 information from an applicant dossier (PDF page texts).

    Strategy
    --------
    1. Scan pages for the first occurrence of a 3.2.S.5 heading pattern.
    2. Collect all lines from that page onwards until a *different* CTD major
       section heading is encountered (3.2.S.6, 3.2.P.*, 3.3.*, etc.) or the
       document ends — whichever comes first.
    3. Within the collected block, attempt coarse sub-section tagging using
       _S5_SUBSECTION_MAP so that retrieval can filter by field name.
    4. Return one ExtractionResult per recognised sub-section, plus one
       "full_s5_block" result carrying the complete raw text for fallback use.
    5. If no S.5 heading is found, fall back to returning all pages as generic
       results (identical to _extract_pdf_pages_generic) so the upload still
       succeeds; a warning is added.

    Returns
    -------
    list[ExtractionResult]  — never empty; at minimum contains the full-block
                              result or the generic page results.
    """
    # Import here to avoid circular imports at module level
    from models import ExtractionResult  # noqa: PLC0415

    results: list[ExtractionResult] = []

    # --- Step 1: locate the S.5 section ---
    s5_start_page: int | None = None
    s5_start_offset = 0
    for page_idx, text in enumerate(raw_text_pages):
        heading_match = _S5_HEADING_RE.search(text)
        if heading_match:
            s5_start_page = page_idx
            s5_start_offset = heading_match.start()
            break

    if s5_start_page is None:
        warnings.append(
            "No CTD 3.2.S.5 heading found in dossier; returning all pages as "
            "generic extractions.  Confirm the document contains section 3.2.S.5."
        )
        return _extract_pdf_pages_generic(raw_text_pages, doc_id, source_type, warnings)

    # --- Step 2: collect the S.5 block ---
    _OTHER_CTD_SECTION_RE = re.compile(
        r"^\s*3\.2\.S\.[6-9]|^\s*3\.2\.P\.|^\s*3\.3\.|^\s*4\.\d",
        re.IGNORECASE | re.MULTILINE,
    )
    s5_lines: list[str] = []
    for page_idx in range(s5_start_page, len(raw_text_pages)):
        page_text = raw_text_pages[page_idx]
        if page_idx == s5_start_page:
            page_text = page_text[s5_start_offset:]
        next_section = _OTHER_CTD_SECTION_RE.search(page_text)
        if next_section:
            page_text = page_text[:next_section.start()]
            if page_text.strip():
                s5_lines.append(page_text)
            break
        if page_text.strip():
            s5_lines.append(page_text)

    full_s5_text = "\n".join(s5_lines)

    # --- Step 3 & 4: tag sub-sections ---
    current_section: str = "general"
    current_lines: list[str] = []
    section_texts: dict[str, list[str]] = {current_section: []}

    for line in full_s5_text.splitlines():
        matched_section: str | None = None
        for pattern, field_name in _S5_SUBSECTION_MAP:
            if pattern.search(line):
                matched_section = field_name
                break
        if matched_section and matched_section != current_section:
            section_texts[current_section] = current_lines
            current_section = matched_section
            current_lines = section_texts.get(current_section, [])
            section_texts[current_section] = current_lines
        current_lines.append(line)

    section_texts[current_section] = current_lines

    for section_name, lines in section_texts.items():
        text = "\n".join(lines).strip()
        if not text:
            continue
        results.append(
            ExtractionResult(
                doc_id=doc_id,
                source_type=source_type,
                section_id=f"S5-DOSSIER-{section_name.upper().replace('_', '-')}",
                section_title=section_name.replace("_", " ").title(),
                raw_text=text,
                page_or_line=f"p.{s5_start_page + 1}",
                notes=[f"ctd_section=3.2.S.5 subsection={section_name}"],
            )
        )

    # Always add a full-block result for unstructured retrieval fallback
    results.append(
        ExtractionResult(
            doc_id=doc_id,
            source_type=source_type,
            section_id="S5-DOSSIER-FULL-BLOCK",
            section_title="3.2.S.5 Full Block",
            raw_text=full_s5_text,
            page_or_line=f"p.{s5_start_page + 1}",
            notes=["ctd_section=3.2.S.5 subsection=full_block"],
        )
    )

    return results
