"""Command-line entry point: ingest one dossier PDF, write a case JSON.

Usage:
    python -m m3.cli path/to/dossier.pdf --case-id CASE-001 --out out.json
"""
from __future__ import annotations

import argparse

from .export import require_separate_output, write_case_json
from .pipeline import ingest_dossier, ingest_dossier_files


def main() -> None:
    parser = argparse.ArgumentParser(description="M3 Tier-0 dossier ingestion")
    parser.add_argument("pdf_path", nargs="+", help="Paths to dossier PDFs")
    parser.add_argument("--case-id", default="CASE-LOCAL", help="Case identifier")
    parser.add_argument("--document-id", default=None, help="Defaults to the PDF filename")
    parser.add_argument("--ocr-language", default="eng", help="Installed Tesseract language code(s)")
    parser.add_argument("--out", default="case_output.json")
    args = parser.parse_args()

    if args.document_id and len(args.pdf_path) != 1:
        parser.error("--document-id requires exactly one PDF")
    try:
        require_separate_output(args.out, args.pdf_path)
        if args.document_id:
            chunks = ingest_dossier(args.pdf_path[0], document_id=args.document_id,
                                    ocr_language=args.ocr_language)
        else:
            chunks = ingest_dossier_files(args.pdf_path, ocr_language=args.ocr_language)
        out_path = write_case_json(args.out, args.case_id, chunks)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"m3-ingest: {exc}\n")

    flagged = [c for c in chunks if c.quality_flag]
    print(f"Ingested {len(chunks)} chunks ({len(flagged)} flagged) -> {out_path}")
    sections = sorted({c.ctd_section for c in chunks})
    print("Sections seen:", ", ".join(sections))
    if not any(not chunk.quality_flag for chunk in chunks):
        parser.exit(2, "m3-ingest: no reviewable content; inspect the flagged output.\n")


if __name__ == "__main__":
    main()
