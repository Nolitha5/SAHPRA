// Page numbers: `page_number` is the PDF page (position in the file, what a PDF viewer jumps to);
// `page_label` is the number PRINTED on that page (e.g. "3", "iv", "317"), when it could be read.

/** "p.3 (PDF p.7)" when they differ, "p.7" otherwise; `short` gives "3 (PDF 7)" / "7" for tables. */
export function pageText(pageNumber: number | null | undefined, pageLabel?: string | null, short = false): string {
  if (pageNumber == null) return short ? 'n/a' : ''
  if (pageLabel && pageLabel !== String(pageNumber)) {
    return short ? `${pageLabel} (PDF ${pageNumber})` : `p.${pageLabel} (PDF p.${pageNumber})`
  }
  return short ? String(pageNumber) : `p.${pageNumber}`
}
