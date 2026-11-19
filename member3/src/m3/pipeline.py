"""Convert eCTD drug substance PDFs into page-cited, redacted chunks."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path

from .chunking import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP, SectionBlock, chunk_section_blocks
from .ctd_mapping import SectionTracker, detect_heading
from .extraction import LayoutItem, PageText, extract_pages
from .language import detect_language
from .pii_filter import scan_and_redact
from .schemas import DossierChunk

_CAPTION = re.compile(r"^(?:figure|fig\.)\s+[A-Z0-9][\w.\-]*\s*[:.\-–]", re.I)
_TOC = re.compile(r"^\s*(?:table of contents|contents)\s*$", re.I)
_TOC_ENTRY = re.compile(r"(?:[.·…]{2,}\s*|\s{2,})\d+\s*$")
_OUTSIDE_S = re.compile(r"^3\.2\.[PAR](?:\.\d+)*\b", re.I)


def _looks_garbled(text: str) -> bool:
    readable = sum(c.isalnum() or c.isspace() for c in text)
    return not any(c.isalnum() for c in text) or readable / len(text) < 0.6


def _digest(path: Path) -> str:
    with path.open("rb") as source:
        digest = hashlib.sha256()
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
        return digest.hexdigest()


def ingest_dossier(
    pdf_path: str | Path,
    document_id: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_OVERLAP,
    *,
    ocr_language: str = "eng",
) -> list[DossierChunk]:
    """Ingest one PDF. Every emitted item is traceable to one physical page."""
    path = Path(pdf_path)
    return _ingest_pdf(path, document_id or path.name, _digest(path), ocr_language,
                       chunk_size, chunk_overlap)


def _ingest_pdf(
    path: Path, document_id: str, source_digest: str, ocr_language: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_OVERLAP,
) -> list[DossierChunk]:
    if chunk_size < 1 or not 0 <= chunk_overlap < chunk_size:
        raise ValueError("Chunk size must be positive and overlap must be smaller than size.")
    document_id = scan_and_redact(document_id).redacted_text
    tracker = SectionTracker()
    chunks: list[DossierChunk] = []
    page_sequences: dict[int, int] = {}
    heading_page: PageText | None = None

    for page in extract_pages(path, ocr_language=ocr_language):
        items = page.items if page.items is not None else [
            LayoutItem("text", line) for line in page.text.splitlines()
        ]
        pending: list[str] = []

        def emit(text: str = "", *, kind: str = "text", rows: list[dict] | None = None,
                 hits: list[str] | None = None, flag: str | None = None,
                 original_page: PageText | None = None, attribute_section: bool = True) -> None:
            source_page = original_page or page
            sequence = page_sequences.get(source_page.page, 0)
            section = (tracker.current if attribute_section else None) or "UNKNOWN"
            identity = f"{source_digest}\x1f{document_id}\x1f{source_page.page}\x1f{section}\x1f{sequence}"
            chunks.append(DossierChunk(
                chunk_id="m3-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
                document_id=document_id, ctd_section=section, page=source_page.page,
                kind=kind, text=text, table_rows=rows or [],
                metadata={"section_confidence": tracker.current_confidence if attribute_section else 0.0,
                          "extraction_source": source_page.source, "pii_redactions": hits or [],
                          "source_sha256": source_digest},
                quality_flag=flag or ("CTD_SECTION_UNKNOWN" if section == "UNKNOWN" else None),
            ))
            page_sequences[source_page.page] = sequence + 1

        def flush() -> None:
            if not pending:
                return
            original = "\n".join(pending)
            pending.clear()
            scan = scan_and_redact(original)
            garbled = _looks_garbled(original)
            block = SectionBlock(tracker.current or "UNKNOWN", scan.redacted_text)
            for chunk in chunk_section_blocks([block], chunk_size, chunk_overlap):
                flag = "GARBLED_OR_EMPTY_EXTRACTION" if garbled or _looks_garbled(chunk.text) else None
                emit(chunk.text, hits=scan.hits, flag=flag)

        def close_empty_section() -> None:
            nonlocal heading_page
            if heading_page is not None:
                emit(flag="EMPTY_SECTION", original_page=heading_page)
                heading_page = None

        if page.source == "empty":
            close_empty_section()
            emit(flag=page.issues[0] if page.issues else "EMPTY_EXTRACTION", attribute_section=False)
            # A missing page could contain a heading. Require a new anchor.
            tracker = SectionTracker()
            continue
        for issue in page.issues:
            emit(flag=issue, attribute_section=False)
        lines = [item.text.strip() for item in items if item.text.strip()]
        if lines and (_TOC.fullmatch(lines[0]) or (
            sum(bool(_TOC_ENTRY.search(line)) for line in lines) >= 2
            and all(detect_heading(line) is None for line in lines)
        )):
            emit(flag="TABLE_OF_CONTENTS_SKIPPED", attribute_section=False)
            continue
        for item in items:
            if item.kind == "table":
                heading_page = None
                flush()
                rows: list[dict] = []
                hits: list[str] = []
                for cells in item.rows or []:
                    row = {}
                    for index, value in enumerate(cells, 1):
                        if value is None:
                            row[f"column_{index}"] = None
                            continue
                        scan = scan_and_redact(unicodedata.normalize("NFC", value))
                        row[f"column_{index}"] = scan.redacted_text
                        hits.extend(scan.hits)
                    rows.append(row)
                text = "\n".join(" | ".join(value or "" for value in row.values()) for row in rows)
                flag = None if any(value and value.strip() for row in rows for value in row.values()) else "EMPTY_TABLE"
                emit(text, kind="table", rows=rows, hits=hits, flag=flag)
                continue
            line = unicodedata.normalize("NFC", item.text).strip()
            if not line:
                continue
            match = detect_heading(line, ocr=page.source == "ocr")
            if match is not None:
                flush()
                close_empty_section()
                tracker.set_heading(match)
                heading_page = page
            elif _OUTSIDE_S.match(line):
                flush()
                close_empty_section()
                tracker = SectionTracker()
            elif _CAPTION.match(line):
                heading_page = None
                flush()
                scan = scan_and_redact(line)
                emit(scan.redacted_text, kind="figure_caption", hits=scan.hits)
            else:
                heading_page = None
                pending.append(line)
        flush()
        if page.page not in page_sequences and heading_page is None:
            emit(flag="EMPTY_EXTRACTION")
    if heading_page is not None:
        close_empty_section()
    chunks.sort(key=lambda chunk: chunk.page or 0)
    sample: list[str] = []
    sample_chars = 0
    for chunk in chunks:
        if chunk.kind != "text" or chunk.quality_flag:
            continue
        sample.append(re.sub(r"\[REDACTED_[A-Z_]+\]", "", chunk.text))
        sample_chars += len(sample[-1])
        if sample_chars >= 10_000:
            break
    language, confidence = detect_language(" ".join(sample)[:10_000])
    for chunk in chunks:
        chunk.metadata.update(language=language, language_confidence=confidence)
    return chunks


def ingest_dossier_files(
    pdf_paths: Iterable[str | Path], *, ocr_language: str = "eng",
) -> list[DossierChunk]:
    """Ingest a case, skipping byte-identical uploads without merging citations."""
    paths = [Path(path) for path in pdf_paths]
    if not paths:
        raise ValueError("Provide at least one dossier PDF.")
    seen: set[str] = set()
    chunks: list[DossierChunk] = []
    for path in paths:
        digest = _digest(path)
        if digest in seen:
            continue
        seen.add(digest)
        document_id = f"{path.name}#{digest[:16]}" if len(paths) > 1 else path.name
        chunks.extend(_ingest_pdf(path, document_id, digest, ocr_language))
    return chunks
