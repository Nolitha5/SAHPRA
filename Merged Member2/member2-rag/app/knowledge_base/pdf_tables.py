"""Tables in the source PDFs: found at conversion time, shown as real tables in results.

Passage text (and therefore search) is not changed: tables are stored next to the
passages, keyed by document and PDF page, and shown with the passages of that page.

For every table we keep
  * the cell text, read from each cell's own area of the page (this keeps decimal
    points and spaces where they are printed: "0.05%", "Carbon tetrachloride"),
  * an image of the original table cut from the PDF, so an assessor can always
    check the exact printed values.

Uses PyMuPDF's table finder. Tables drawn without lines may not be found; their
text stays in the passages as before.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

TABLE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,159}$")
IMAGE_DPI = 150
MIN_ROWS, MIN_COLS, MIN_FILLED_CELLS = 2, 2, 4


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


_SUPERSCRIPT = str.maketrans("0123456789()+-=abcdefghijklmnoprstuvwxyz",
                             "⁰¹²³⁴⁵⁶⁷⁸⁹⁽⁾⁺⁻⁼ᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐⁿᵒᵖʳˢᵗᵘᵛʷˣʸᶻ")


def _cell_text(page: Any, rect: Any) -> str:
    """Text inside one table cell. Superscript characters (footnote markers) are written as
    superscripts, so "0.12" with footnote 1 reads "0.12¹⁾", never "0.121)"."""
    lines = []
    for block in page.get_text("dict", clip=rect)["blocks"]:
        for line in block.get("lines", []):
            parts = []
            for span in line["spans"]:
                text = span["text"]
                if span["flags"] & 1 and text.strip():  # PyMuPDF flag bit 0: superscript
                    text = text.strip().translate(_SUPERSCRIPT)
                parts.append(text)
            lines.append("".join(parts))
    return _clean(" ".join(lines))


def _drop_empty_columns(rows: list[list[str]]) -> list[list[str]]:
    keep = [i for i in range(max(map(len, rows), default=0)) if any(i < len(r) and r[i] for r in rows)]
    return [[r[i] if i < len(r) else "" for i in keep] for r in rows]


def extract_tables(
    pdf: Path,
    id_base: str,
    source_identifier: str,
    document_version: str | None,
    page_labels: list[str | None],
    first_page: int,
    last_page: int | None,
    image_dir: Path,
) -> list[dict[str, Any]]:
    """All tables on pages first_page..last_page, with cell text and an image file each."""
    import pymupdf  # only needed when converting PDFs

    image_dir.mkdir(parents=True, exist_ok=True)
    tables: list[dict[str, Any]] = []
    with pymupdf.open(str(pdf)) as doc:
        last = min(last_page or doc.page_count, doc.page_count)
        for page_no in range(first_page, last + 1):
            page = doc[page_no - 1]
            for index, table in enumerate(page.find_tables().tables, start=1):
                rows = [
                    [_cell_text(page, pymupdf.Rect(cell)) if cell else "" for cell in row.cells]
                    for row in table.rows
                ]
                rows = _drop_empty_columns([r for r in rows if any(r)])
                filled = sum(1 for r in rows for c in r if c)
                if len(rows) < MIN_ROWS or (rows and len(rows[0]) < MIN_COLS) or filled < MIN_FILLED_CELLS:
                    continue  # not a real table (a box, a single line, a layout frame)
                table_id = f"{id_base}-p{page_no}-t{index}".lower()
                x0, y0, x1, y1 = table.bbox
                clip = pymupdf.Rect(x0 - 4, y0 - 4, x1 + 4, y1 + 4)  # a small margin around the lines
                pix = page.get_pixmap(clip=clip & page.rect, dpi=IMAGE_DPI)
                image_name = f"{table_id}.png"
                pix.save(str(image_dir / image_name))
                tables.append({
                    "table_id": table_id,
                    "source_identifier": source_identifier,
                    "document_version": document_version,
                    "page_number": page_no,
                    "page_label": page_labels[page_no - 1] if page_no - 1 < len(page_labels) else None,
                    "index_on_page": index,
                    "rows": rows,
                    "image": image_name,
                    "width": pix.width,
                    "height": pix.height,
                })
    return tables


def write_tables_file(path: Path, image_dir: Path, tables: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rel = Path(image_dir).resolve().relative_to(path.parent.resolve(), walk_up=True)
    path.write_text(json.dumps({"image_dir": rel.as_posix(), "tables": tables}, ensure_ascii=False, indent=1),
                    encoding="utf-8")


class TableStore:
    """Read-only access to the tables file, reloaded when it changes on disk."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._mtime: float | None = None
        self._by_page: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        self._by_id: dict[str, dict[str, Any]] = {}
        self._image_dir = self.path.parent

    def _load(self) -> None:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            self._by_page, self._by_id, self._mtime = {}, {}, None
            return
        if mtime == self._mtime:
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._image_dir = (self.path.parent / data.get("image_dir", ".")).resolve()
        by_page: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
        by_id: dict[str, dict[str, Any]] = {}
        for t in data.get("tables", []):
            if not TABLE_ID_RE.match(str(t.get("table_id", ""))):
                continue
            key = (t["source_identifier"], t.get("document_version") or "", int(t["page_number"]))
            by_page.setdefault(key, []).append(t)
            by_id[t["table_id"]] = t
        self._by_page, self._by_id, self._mtime = by_page, by_id, mtime

    def for_page(self, source_identifier: str, document_version: str | None, page_number: int | None) -> list[dict]:
        if page_number is None:
            return []
        self._load()
        return self._by_page.get((source_identifier, document_version or "", int(page_number)), [])

    def image_path(self, table_id: str) -> Path | None:
        """The PNG of a known table; None for unknown ids (no path is ever built from user input)."""
        if not TABLE_ID_RE.match(table_id):
            return None
        self._load()
        table = self._by_id.get(table_id)
        if table is None:
            return None
        path = (self._image_dir / table["image"]).resolve()
        return path if path.is_file() and path.parent == self._image_dir else None

    def count(self) -> int:
        self._load()
        return len(self._by_id)
