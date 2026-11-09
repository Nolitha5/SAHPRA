"""
Text & layout extraction from eCTD Module 3.2.S PDFs.

PyMuPDF (imported as `pymupdf`, the non-deprecated name) is the primary
extractor — fast and reliable for born-digital pages. When a page yields
(near-)no extractable text, it's treated as scanned and handed to the OCR
fallback (pytesseract + the page rendered to an image via PyMuPDF itself,
so no extra PDF->image dependency is needed).

Docling / Unstructured / Marker (per the M3 tool list) are the next layer
to plug in for proper table/figure structure — this module only emits
plain text per page plus a per-page "looks scanned" flag; table extraction
lives in tables.py so it can be swapped independently.
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


def _ocr_page(doc, page_index: int, zoom: float = 2.0) -> str:
    if pytesseract is None or pymupdf is None:
        return ""
    page = doc[page_index]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    img_bytes = pix.tobytes("png")
    from io import BytesIO

    image = Image.open(BytesIO(img_bytes))
    return pytesseract.image_to_string(image)


def extract_pages(pdf_path: str | Path) -> list[PageText]:
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
        for i, page in enumerate(doc):
            native_text = page.get_text("text") or ""
            if len(native_text.strip()) >= SCANNED_TEXT_THRESHOLD:
                pages.append(PageText(page=i + 1, text=native_text, source="native"))
                continue
            ocr_text = _ocr_page(doc, i)
            if ocr_text.strip():
                pages.append(PageText(page=i + 1, text=ocr_text, source="ocr"))
            else:
                pages.append(PageText(page=i + 1, text="", source="empty"))
    return pages
