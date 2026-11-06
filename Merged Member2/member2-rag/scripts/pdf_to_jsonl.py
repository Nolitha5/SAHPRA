"""TEMPORARY stand-in for Member 3's ingestion pipeline.

Converts text-based PDFs (for example public ICH guidelines) into processed
passages in exactly the JSONL format `load_documents.py` expects, so retrieval
and the benchmark can be tested on real regulatory text before Member 3's data
is ready.

What it does
  * reads each page's text with pypdf (page numbers stay exact),
  * removes header/footer lines that repeat on most pages,
  * splits each page into overlapping word chunks (a chunk never spans pages),
  * attaches the source details YOU supply from the document's cover page,
  * optionally tags CTD sections by page range,
  * validates every record with the same Pydantic model as the loader.

What it does NOT do (Member 3's job): OCR of scanned pages, table extraction,
automatic CTD mapping, section-aware chunking. Pages with no extractable text
are reported, not guessed.

Never invent metadata: copy version and date from the document itself. Values
containing "FILL" are rejected so template placeholders cannot slip through.

Examples (from the member2-rag folder):
    python scripts/pdf_to_jsonl.py --manifest data/raw/manifest.json --output data/processed/ich_pilot_c300.jsonl

    python scripts/pdf_to_jsonl.py --pdf data/raw/ICH_Q6A.pdf --title "..." --org ICH \
        --identifier "ICH Q6A" --version "..." --date 1999-10 --status current \
        --page-sections "1-3:3.2.S.4,4-12:3.2.S.4.1" --output data/processed/q6a.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from app.schemas import ApplicabilityStatus, DocumentType, PassageRecord, normalise_ctd_section

MIN_PAGE_CHARS = 40  # below this a page is treated as having no extractable text
_SLUG = re.compile(r"[^A-Za-z0-9]+")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass
class SourceDoc:
    pdf: Path
    source_title: str
    issuing_organization: str
    source_identifier: str
    document_version: str | None = None
    publication_date: str | None = None
    effective_date: str | None = None
    applicability_status: str = "unknown"
    document_type: str = "guideline"
    ctd_section: str | None = None  # default for every page
    page_sections: dict[int, str] = field(default_factory=dict)  # page -> section
    first_page: int = 1
    last_page: int | None = None


@dataclass
class ConvertReport:
    pdf: str
    pages_total: int = 0
    pages_used: int = 0
    pages_without_text: list[int] = field(default_factory=list)
    header_footer_lines_removed: int = 0
    chunks: int = 0
    rejected: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def slug(value: str) -> str:
    return _SLUG.sub("-", value).strip("-").lower() or "x"


def parse_page_sections(spec: str | None) -> dict[int, str]:
    """'1-3:3.2.S.4,4-12:3.2.S.4.1,15:3.2.S.4.3' -> {page: section}."""
    out: dict[int, str] = {}
    if not spec:
        return out
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            pages, section = part.split(":", 1)
            if "-" in pages:
                start, end = (int(x) for x in pages.split("-", 1))
            else:
                start = end = int(pages)
        except ValueError:
            raise ValueError(f"bad --page-sections item {part!r}; use e.g. 4-12:3.2.S.4.1") from None
        if start < 1 or end < start:
            raise ValueError(f"bad page range in {part!r}")
        norm = normalise_ctd_section(section)
        if norm is None:
            raise ValueError(f"missing CTD section in {part!r}")
        for page in range(start, end + 1):
            out[page] = norm
    return out


def check_no_placeholder(doc: SourceDoc) -> None:
    for name in ("source_title", "source_identifier", "document_version", "publication_date", "effective_date"):
        value = getattr(doc, name)
        if value and "FILL" in value.upper():
            raise ValueError(
                f"{doc.pdf.name}: '{name}' still contains a placeholder ({value!r}). "
                "Copy the real value from the document's cover page, or leave it empty."
            )
    DocumentType(doc.document_type)
    ApplicabilityStatus(doc.applicability_status)


def extract_pages(pdf: Path) -> list[str]:
    """Page texts. pypdf's layout mode places glyphs by position, which avoids
    most words split by kerning ("shou ld"); plain mode is the per-page fallback."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("pypdf is not installed. Run: pip install -r requirements.txt") from exc
    reader = PdfReader(str(pdf))
    pages = []
    for page in reader.pages:
        text = ""
        for kwargs in ({"extraction_mode": "layout"}, {}):
            try:
                text = page.extract_text(**kwargs) or ""
            except Exception:  # a single broken page should not stop the document
                continue
            if len(text.strip()) >= MIN_PAGE_CHARS:  # layout mode can miss text on some pages
                break
        pages.append(text)
    return pages


def _norm_line(line: str) -> str:
    # Page numbers inside headers/footers change per page; mask digits when comparing.
    return re.sub(r"\d+", "#", line.strip().lower())


def _edge_count(n_lines: int, edge: int) -> int:
    # Short pages: only look at the very first and last line, so body text survives.
    return max(1, min(edge, n_lines // 4))


def _edge_lines(text: str, n: int) -> list[str]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    k = _edge_count(len(lines), n)
    return lines[:k] + lines[-k:]


def remove_repeating_lines(pages: list[str], min_share: float = 0.5, edge: int = 3) -> tuple[list[str], int]:
    """Drop running headers/footers: lines in the top or bottom `edge` lines of a
    page that recur (digits ignored) on at least `min_share` of pages. Body text
    is never touched, even if a sentence repeats on many pages."""
    if len(pages) < 3:
        return pages, 0
    counts: Counter[str] = Counter()
    for text in pages:
        counts.update({_norm_line(ln) for ln in _edge_lines(text, edge)})
    threshold = max(2, int(len(pages) * min_share))
    repeating = {line for line, n in counts.items() if n >= threshold and len(line) < 150}
    removed = 0
    cleaned = []
    for text in pages:
        lines = text.splitlines()
        nonblank = [i for i, ln in enumerate(lines) if ln.strip()]
        k = _edge_count(len(nonblank), edge)
        edge_idx = set(nonblank[:k] + nonblank[-k:])
        keep = []
        for i, line in enumerate(lines):
            if i in edge_idx and _norm_line(line) in repeating:
                removed += 1
                continue
            keep.append(line)
        cleaned.append("\n".join(keep))
    return cleaned, removed


# Word/PDF "Symbol" font glyphs land in the Unicode private use area (U+F0xx).
_SYMBOL_FONT = {
    "": "•", "": "▪", "": "•", "": "≤", "": "≥", "": "±",
    "": "×", "": "→", "": "(", "": ")", "": "−", "": "=",
    "": "+", "": "<", "": ">", "": "µ", "": "°",
}
_SYMBOL_RE = re.compile("|".join(map(re.escape, _SYMBOL_FONT)))
_WORD = re.compile(r"[A-Za-z]+")
_HEAD = re.compile(r"^(\W*)([A-Za-z]+)$")  # "(shou" -> "(", "shou"
_TAIL = re.compile(r"^([a-z]+)(\W*)$")  # "ld," -> "ld", ","


def clean_text(text: str) -> str:
    text = _SYMBOL_RE.sub(lambda m: _SYMBOL_FONT[m.group()], text)
    text = re.sub(r"(\w)-[ \t]*\n[ \t]*(\w)", r"\1\2", text)  # join words hyphenated across lines
    return re.sub(r"\s+", " ", text).strip()


def word_counts(texts: list[str]) -> Counter[str]:
    return Counter(w.lower() for t in texts for w in _WORD.findall(t))


def repair_split_words(text: str, counts: Counter[str], min_joined: int = 3) -> str:
    """Rejoin words that PDF extraction split in two ("shou ld" -> "should").

    A pair is joined only when the joined form occurs at least `min_joined`
    times as a whole word in the same document AND one piece is rarer than the
    joined word (a fragment). Two common words ("can not", "in to") are never
    merged, so ordinary text is left alone.
    """
    def should_join(pieces: list[str]) -> bool:
        n = counts.get("".join(pieces).lower(), 0)
        if n < min_joined:
            return False
        rarest = min(counts.get(p.lower(), 0) for p in pieces)
        return rarest < n or any(len(p) == 1 and p != "a" for p in pieces[1:])

    tokens = text.split(" ")
    out: list[str] = []
    i = 0
    while i < len(tokens):
        head = _HEAD.match(out[-1]) if out else None
        joined = False
        if head:
            # Try 2 then 3 pieces, so a word split twice ("de fine d") is found.
            for width in (1, 2):
                tails = [_TAIL.match(t) for t in tokens[i : i + width]]
                if len(tails) < width or not all(tails):
                    break
                # Inner pieces must be bare letters; only the last may carry punctuation.
                if any(m.group(2) for m in tails[:-1]):
                    break
                if should_join([head.group(2)] + [m.group(1) for m in tails]):
                    out[-1] += "".join(tokens[i : i + width])
                    i += width
                    joined = True
                    break
        if not joined:
            out.append(tokens[i])
            i += 1
    return " ".join(out)


def chunk_words(text: str, size: int, overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = size - overlap
    chunks = []
    for start in range(0, len(words), step):
        piece = words[start : start + size]
        if chunks and len(piece) <= overlap:  # only repeated overlap left
            break
        chunks.append(" ".join(piece))
        if start + size >= len(words):
            break
    return chunks


# ---------------------------------------------------------------------------
# Conversion
# ---------------------------------------------------------------------------
def convert(doc: SourceDoc, chunk_size: int, overlap: int) -> tuple[list[dict], ConvertReport]:
    check_no_placeholder(doc)
    report = ConvertReport(pdf=doc.pdf.name)
    raw_pages = extract_pages(doc.pdf)
    report.pages_total = len(raw_pages)
    pages, report.header_footer_lines_removed = remove_repeating_lines(raw_pages)

    last = doc.last_page or len(pages)
    id_base = f"{slug(doc.source_identifier)}-{slug(doc.document_version or 'nover')}"
    cleaned = [clean_text(p) for p in pages]
    counts = word_counts(cleaned)
    records: list[dict] = []
    for page_no in range(doc.first_page, min(last, len(pages)) + 1):
        text = repair_split_words(cleaned[page_no - 1], counts)
        if len(text) < MIN_PAGE_CHARS:
            report.pages_without_text.append(page_no)
            continue
        report.pages_used += 1
        section = doc.page_sections.get(page_no, doc.ctd_section)
        for idx, chunk in enumerate(chunk_words(text, chunk_size, overlap)):
            row = {
                "chunk_id": f"{id_base}-p{page_no}-c{idx}-w{chunk_size}",
                "text": chunk,
                "source_title": doc.source_title,
                "issuing_organization": doc.issuing_organization,
                "source_identifier": doc.source_identifier,
                "document_version": doc.document_version,
                "publication_date": doc.publication_date,
                "effective_date": doc.effective_date,
                "page_number": page_no,
                "ctd_section": section,
                "document_type": doc.document_type,
                "applicability_status": doc.applicability_status,
                "chunk_index": idx,
                "chunk_size": chunk_size,
                "chunk_overlap": overlap,
                "language": "en",
            }
            row = {k: v for k, v in row.items() if v not in (None, "")}
            try:
                PassageRecord(**row).to_metadata()
            except ValidationError as exc:
                fields = sorted({".".join(map(str, e["loc"])) for e in exc.errors()})
                report.rejected.append(f"page {page_no} chunk {idx}: invalid {fields}")
                continue
            records.append(row)
    report.chunks = len(records)
    return records, report


def doc_from_dict(d: dict, base: Path) -> SourceDoc:
    pdf = Path(d["pdf"])
    if not pdf.is_absolute():
        pdf = (base / pdf).resolve()
    return SourceDoc(
        pdf=pdf,
        source_title=d["source_title"],
        issuing_organization=d["issuing_organization"],
        source_identifier=d["source_identifier"],
        document_version=d.get("document_version") or None,
        publication_date=d.get("publication_date") or None,
        effective_date=d.get("effective_date") or None,
        applicability_status=d.get("applicability_status", "unknown"),
        document_type=d.get("document_type", "guideline"),
        ctd_section=normalise_ctd_section(d.get("ctd_section")),
        page_sections=parse_page_sections(d.get("page_sections")),
        first_page=int(d.get("first_page", 1)),
        last_page=int(d["last_page"]) if d.get("last_page") else None,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manifest", type=Path, help="JSON list of documents (see data/raw/manifest.example.json)")
    p.add_argument("--pdf", type=Path, help="a single PDF (instead of --manifest)")
    p.add_argument("--title")
    p.add_argument("--org")
    p.add_argument("--identifier", help="official document code or URL, e.g. 'ICH Q6A'")
    p.add_argument("--version")
    p.add_argument("--date", help="publication date: YYYY, YYYY-MM or YYYY-MM-DD")
    p.add_argument("--effective-date")
    p.add_argument("--status", default="unknown", choices=[s.value for s in ApplicabilityStatus])
    p.add_argument("--doc-type", default="guideline", choices=[t.value for t in DocumentType])
    p.add_argument("--ctd-section", help="CTD section for every page")
    p.add_argument("--page-sections", help="per-page CTD sections, e.g. '1-3:3.2.S.4,4-12:3.2.S.4.1'")
    p.add_argument("--first-page", type=int, default=1, help="skip cover/contents pages before this")
    p.add_argument("--last-page", type=int, help="skip annexes/references after this")
    p.add_argument("--chunk-size", type=int, default=300, help="words per chunk (about 400 tokens)")
    p.add_argument("--overlap", type=int, default=50, help="words shared between neighbouring chunks")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)

    if not 50 <= args.chunk_size <= 1000:
        p.error("--chunk-size must be between 50 and 1000 words")
    if not 0 <= args.overlap < args.chunk_size:
        p.error("--overlap must be >= 0 and smaller than --chunk-size")

    try:
        if args.manifest:
            entries = json.loads(args.manifest.read_text(encoding="utf-8"))
            docs = [doc_from_dict(d, args.manifest.parent) for d in entries]
        elif args.pdf:
            missing = [n for n in ("title", "org", "identifier") if not getattr(args, n)]
            if missing:
                p.error(f"--pdf also needs: {', '.join('--' + m for m in missing)}")
            docs = [doc_from_dict({
                "pdf": str(args.pdf.resolve()), "source_title": args.title, "issuing_organization": args.org,
                "source_identifier": args.identifier, "document_version": args.version,
                "publication_date": args.date, "effective_date": args.effective_date,
                "applicability_status": args.status, "document_type": args.doc_type,
                "ctd_section": args.ctd_section, "page_sections": args.page_sections,
                "first_page": args.first_page, "last_page": args.last_page,
            }, Path.cwd())]
        else:
            p.error("give --manifest or --pdf")
    except (ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    all_rows: list[dict] = []
    reports = []
    for doc in docs:
        if not doc.pdf.exists():
            print(f"ERROR: PDF not found: {doc.pdf}", file=sys.stderr)
            return 1
        try:
            rows, report = convert(doc, args.chunk_size, args.overlap)
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        all_rows.extend(rows)
        reports.append(report)

    ids = [r["chunk_id"] for r in all_rows]
    if len(ids) != len(set(ids)):
        print("ERROR: duplicate chunk IDs; two documents share identifier and version.", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in all_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "output": str(args.output),
        "chunk_size_words": args.chunk_size,
        "overlap_words": args.overlap,
        "total_chunks": len(all_rows),
        "documents": [r.__dict__ for r in reports],
        "note": (
            "Temporary stand-in for Member 3's pipeline: no OCR, no tables, "
            "CTD sections only as you supplied them."
        ),
    }
    print(json.dumps(summary, indent=2))
    if any(r.pages_without_text for r in reports):
        print("WARNING: some pages had no extractable text (scanned images?). They were skipped; "
              "they need OCR from Member 3's pipeline.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
