"""
End-to-end M3 ingestion pipeline: one dossier PDF -> list[DossierChunk].

This is the Tier 0 walking-skeleton version per the delegation doc: ingest
one dossier, produce clean chunks for a handful of pages with correct
section tags, hand off in the exact shape M2 already built against. Table
extraction (Docling) and the S.2/S.3 agents are the next layers on top of
this, not required for the thin thread to prove itself.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .chunking import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP, SectionBlock, chunk_section_blocks
from .ctd_mapping import SectionTracker
from .extraction import extract_pages
from .pii_filter import scan_and_redact
from .schemas import DossierChunk

# A line is "garbled" if it has an unusually high ratio of non-alphanumeric,
# non-space characters — typical of a failed OCR pass or extraction noise.
_GARBLED_RATIO = 0.4
_MIN_CHUNK_CHARS = 10


def _looks_garbled(text: str) -> bool:
    if not text.strip():
        return True
    alnum_or_space = sum(1 for c in text if c.isalnum() or c.isspace())
    return (alnum_or_space / len(text)) < (1 - _GARBLED_RATIO)


def _chunk_id(document_id: str, ctd_section: str, page: int | None, idx: int) -> str:
    raw = f"{document_id}|{ctd_section}|{page}|{idx}"
    return "m3-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def ingest_dossier(
    pdf_path: str | Path,
    document_id: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_OVERLAP,
) -> list[DossierChunk]:
    """Ingest one dossier PDF end-to-end and return DossierChunk objects.

    Garbled or empty extractions are never dropped silently: they come
    through as a chunk with `quality_flag` set, so M2/M4/M5 can see — and
    the assessor can be told — that a part of the dossier could not be
    read, instead of that gap disappearing.
    """
    path = Path(pdf_path)
    document_id = document_id or path.name

    pages = extract_pages(path)

    tracker = SectionTracker()
    blocks: list[SectionBlock] = []
    current_block_lines: list[str] = []
    current_section = None
    current_confidence = 0.0
    current_page = None

    def _flush():
        if current_block_lines and current_section:
            blocks.append(
                SectionBlock(
                    ctd_section=current_section,
                    text="\n".join(current_block_lines),
                    page=current_page,
                    confidence=current_confidence,
                )
            )

    for page_text in pages:
        for line in page_text.text.splitlines():
            match = tracker.feed(line)
            if match is not None:
                _flush()
                current_block_lines = []
                current_section = match.code
                current_confidence = match.confidence
                current_page = page_text.page
                continue
            if tracker.current is None:
                # Content before the first recognised heading (cover page,
                # TOC, etc.) — not attributable to any CTD section; skip
                # rather than mis-tag it.
                continue
            current_block_lines.append(line)
            if current_page is None:
                current_page = page_text.page
    _flush()

    section_chunks = chunk_section_blocks(blocks, size=chunk_size, overlap=chunk_overlap)

    out: list[DossierChunk] = []
    for sc in section_chunks:
        scan = scan_and_redact(sc.text)
        quality_flag = None
        if _looks_garbled(scan.redacted_text) or len(scan.redacted_text.strip()) < _MIN_CHUNK_CHARS:
            quality_flag = "GARBLED_OR_EMPTY_EXTRACTION"
        chunk = DossierChunk(
            chunk_id=_chunk_id(document_id, sc.ctd_section, sc.page, sc.chunk_index),
            document_id=document_id,
            ctd_section=sc.ctd_section,
            text=scan.redacted_text,
            page=sc.page,
            kind="text",
            table_rows=[],
            metadata={
                "section_confidence": sc.section_confidence,
                "pii_redactions": scan.hits,
            },
            quality_flag=quality_flag,
        )
        out.append(chunk)

    # Quality pages that produced nothing attributable at all (e.g. a
    # section with zero recognised heading anywhere) should still be
    # visible as a flagged gap rather than silently missing.
    if not out:
        out.append(
            DossierChunk(
                chunk_id=_chunk_id(document_id, "UNKNOWN", None, 0),
                document_id=document_id,
                ctd_section="UNKNOWN",
                text="",
                page=None,
                kind="text",
                table_rows=[],
                metadata={"reason": "no CTD S.x heading recognised in document"},
                quality_flag="NO_SECTION_HEADINGS_FOUND",
            )
        )
    return out
