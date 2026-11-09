"""Run the S.2 + S.3 agents over an ingested dossier and emit findings JSON.

Usage:
    python -m m3.run_agents path/to/dossier.pdf --case-id CASE-001 --out findings.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import s2_manufacture, s3_characterisation
from .pipeline import ingest_dossier


def run(case_id: str, pdf_path: str | Path) -> list[dict]:
    chunks = ingest_dossier(pdf_path)
    findings = s2_manufacture.review(case_id, chunks) + s3_characterisation.review(case_id, chunks)
    return [f.model_dump(mode="json") for f in findings]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run M3 S.2/S.3 agents over a dossier")
    parser.add_argument("pdf_path")
    parser.add_argument("--case-id", default="CASE-LOCAL")
    parser.add_argument("--out", default="member3/examples/s2_s3_findings.json")
    args = parser.parse_args()

    findings = run(args.case_id, args.pdf_path)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(findings, indent=2), encoding="utf-8")
    print(f"{len(findings)} findings -> {out}")
    for f in findings:
        print(f"  [{f['status']}] {f['ctd_section']} {f['issue_type']}")


if __name__ == "__main__":
    main()
