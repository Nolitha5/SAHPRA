"""
Text & layout extraction from eCTD Module 3.2.S PDFs.

PyMuPDF (imported as `pymupdf`, the non-deprecated name) is the primary
extractor — fast and reliable for born-digital pages. When a page yields
(near-)no extractable text, it's treated as scanned and handed to the OCR
fallback (pytesseract + the page rendered to an image via PyMuPDF itself,
so no extra PDF->image dependency is needed).

Native PDFs also provide positioned text and detectable ruled tables.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import pymupdf  # type: ignore
except ImportError:  # pragma: no cover
    pymupdf = None

try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
except ImportError:  # pragma: no cover
    pytesseract = None
    Image = None

# A page with fewer than this many non-whitespace characters of native text
# is treated as scanned/image-only and routed to OCR.
SCANNED_TEXT_THRESHOLD = 20


@dataclass
class PageText:
    page: int  # 1-indexed, matches how assessors cite pages
    text: str
    source: str  # "native" | "ocr" | "empty"
    items: list[LayoutItem] | None = None
    issues: tuple[str, ...] = ()


@dataclass
class LayoutItem:
    kind: str
    text: str = ""
    rows: list[list[str | None]] | None = None


def _native_layout(page) -> tuple[list[LayoutItem], tuple[str, ...]]:
    """Return native lines and table rows, ordered by position on the page."""
    try:
        # PyMuPDF 2 added layout-model inference by default. For ruled tables,
        # use the page's vector lines to preserve geometry and numerical values.
        options = {"use_layout": False} if int(pymupdf.VersionBind.split(".")[0]) >= 2 else {}
        tables = page.find_tables(**options).tables
        extracted = [(pymupdf.Rect(table.bbox), table.extract()) for table in tables]
    except (AttributeError, RuntimeError, TypeError, ValueError, IndexError):
        extracted = []
        issues = ("TABLE_EXTRACTION_FAILED",)
    else:
        issues = ()
    positioned = []
    for rect, rows in extracted:
        if rows:
            positioned.append((rect.y0, rect.x0, LayoutItem("table", rows=rows)))
    for block in page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
        for line in block.get("lines", []):
            box = pymupdf.Rect(line["bbox"])
            center = ((box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2)
            if any(center in rect for rect, rows in extracted if rows):
                continue
            text = "".join(span["text"] for span in line["spans"])
            positioned.append((box.y0, box.x0, LayoutItem("text", text)))
    positioned.sort(key=lambda entry: entry[:2])
    return [item for _, _, item in positioned], issues


def _ocr_page(doc, page_index: int, zoom: float = 2.0, language: str = "eng") -> str:
    if pytesseract is None or pymupdf is None:
        raise RuntimeError("OCR dependencies are unavailable")
    page = doc[page_index]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    img_bytes = pix.tobytes("png")
    from io import BytesIO

    with Image.open(BytesIO(img_bytes)) as image:
        return pytesseract.image_to_string(image, lang=language, timeout=45)


def extract_pages(pdf_path: str | Path, *, ocr_language: str = "eng") -> list[PageText]:
    """Extract per-page text, falling back to OCR for scanned pages.

    Raises FileNotFoundError / RuntimeError on unreadable input rather than
    returning silently empty results — the pipeline's job is to flag bad
    extractions, never swallow them.
    """
    if pymupdf is None:
        raise RuntimeError(
            "pymupdf is not installed. `pip install -r member3/requirements.txt`."
        )
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"Dossier PDF not found: {path}")

    pages: list[PageText] = []
    with pymupdf.open(path) as doc:
        if not doc.is_pdf or doc.needs_pass or not len(doc):
            raise ValueError("Input must be a nonempty, readable PDF.")
        for i, page in enumerate(doc):
            try:
                native_text = page.get_text("text") or ""
                enough_text = sum(not char.isspace() for char in native_text) >= SCANNED_TEXT_THRESHOLD
                if enough_text or (native_text.strip() and not page.get_image_info()):
                    items, issues = _native_layout(page)
                    pages.append(PageText(i + 1, native_text, "native", items, issues))
                    continue
            except (RuntimeError, ValueError):
                pages.append(PageText(i + 1, "", "empty", issues=("PAGE_EXTRACTION_FAILED",)))
                continue
            try:
                ocr_text = _ocr_page(doc, i, language=ocr_language)
            except (RuntimeError, OSError):
                pages.append(PageText(i + 1, native_text, "empty", issues=("OCR_FAILED",)))
                continue
            if ocr_text.strip():
                pages.append(PageText(i + 1, ocr_text, "ocr"))
            else:
                pages.append(PageText(i + 1, native_text, "empty", issues=("EMPTY_EXTRACTION",)))
    return pages
