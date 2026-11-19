"""Run the S.2 + S.3 agents over an ingested dossier and emit findings JSON.

Usage:
    python -m m3.run_agents path/to/dossier.pdf --case-id CASE-001 --out findings.json
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import s2_manufacture, s3_characterisation
from .agents_common import evidence_from_chunk, make_finding_id
from .export import require_separate_output, write_json
from .pipeline import ingest_dossier_files
from .schemas import DossierChunk, Finding, FindingStatus


def _findings(case_id: str, chunks: list[DossierChunk]) -> list[dict]:
    findings = [
        Finding(
            finding_id=make_finding_id("M3_INGESTION", case_id, chunk.chunk_id),
            case_id=case_id, agent_id="M3_INGESTION", ctd_section=chunk.ctd_section,
            issue_type="extraction_quality", status=FindingStatus.INSUFFICIENT_EVIDENCE,
            sponsor_evidence=[evidence_from_chunk(chunk)],
            rationale="The input was excluded from automated review. Inspect the cited page.",
            uncertainty=1.0, attributes={"quality_flag": chunk.quality_flag},
        )
        for chunk in chunks
        if chunk.quality_flag and chunk.quality_flag != "TABLE_OF_CONTENTS_SKIPPED"
    ]
    findings.extend(s2_manufacture.review(case_id, chunks))
    findings.extend(s3_characterisation.review(case_id, chunks))
    return [f.model_dump(mode="json") for f in findings]


def run(case_id: str, pdf_path: str | Path) -> list[dict]:
    return _findings(case_id, ingest_dossier_files([pdf_path]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M3 S.2/S.3 agents over a dossier")
    parser.add_argument("pdf_path", nargs="+")
    parser.add_argument("--case-id", default="CASE-LOCAL")
    parser.add_argument("--ocr-language", default="eng", help="Installed Tesseract language code(s)")
    parser.add_argument("--out", default="findings.json")
    args = parser.parse_args()

    try:
        require_separate_output(args.out, args.pdf_path)
        chunks = ingest_dossier_files(args.pdf_path, ocr_language=args.ocr_language)
        findings = _findings(args.case_id, chunks)
        out = write_json(args.out, findings)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.exit(1, f"m3-review: {exc}\n")
    print(f"{len(findings)} findings -> {out}")
    for f in findings:
        print(f"  [{f['status']}] {f['ctd_section']} {f['issue_type']}")
    if not any(not chunk.quality_flag for chunk in chunks):
        parser.exit(2, "m3-review: no reviewable content; inspect the quality findings.\n")


if __name__ == "__main__":
    main()
