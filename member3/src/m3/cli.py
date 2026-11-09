"""Command-line entry point: ingest one dossier PDF, write a case JSON.

Usage:
    python -m m3.cli path/to/dossier.pdf --case-id CASE-001 --out out.json
"""
from __future__ import annotations

import argparse

from .export import write_case_json
from .pipeline import ingest_dossier


def main() -> None:
    parser = argparse.ArgumentParser(description="M3 Tier-0 dossier ingestion")
    parser.add_argument("pdf_path", help="Path to one dossier PDF")
    parser.add_argument("--case-id", default="CASE-LOCAL", help="Case identifier")
    parser.add_argument("--document-id", default=None, help="Defaults to the PDF filename")
    parser.add_argument("--out", default="member3/examples/case_output.json")
    args = parser.parse_args()

    chunks = ingest_dossier(args.pdf_path, document_id=args.document_id)
    out_path = write_case_json(args.out, args.case_id, chunks)

    flagged = [c for c in chunks if c.quality_flag]
    print(f"Ingested {len(chunks)} chunks ({len(flagged)} flagged) -> {out_path}")
    sections = sorted({c.ctd_section for c in chunks})
    print("Sections seen:", ", ".join(sections))


if __name__ == "__main__":
    main()
