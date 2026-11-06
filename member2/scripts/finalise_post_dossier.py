"""Post-dossier-build finalisation: update artefacts and rebuild ZIP.

Run after build_dossier_chroma.py completes successfully.
"""
from __future__ import annotations
import json, shutil
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DOSSIER_REPORT_SRC = PROJECT / "local_indexes" / "dossier_chroma" / "DOSSIER_CHROMA_RUN.json"
DOSSIER_REPORT_DEST = PROJECT / "validation" / "DOSSIER_CHROMA_RUN.json"
FINAL_BGE = PROJECT / "validation" / "FINAL_NATIVE_CHROMADB_BGE_REPORT.json"
FINAL_AUDIT = PROJECT / "validation" / "FINAL_SOURCE_AND_CITATION_AUDIT.json"


def main() -> None:
    if not DOSSIER_REPORT_SRC.exists():
        print("ERROR: DOSSIER_CHROMA_RUN.json not found — build must complete first")
        return

    dossier = json.loads(DOSSIER_REPORT_SRC.read_text(encoding="utf-8"))
    print(f"Dossier build: {dossier.get('chunk_count')} chunks, {dossier.get('source_count')} sources")

    # 1. Copy to validation/
    shutil.copy2(str(DOSSIER_REPORT_SRC), str(DOSSIER_REPORT_DEST))
    print(f"Copied to {DOSSIER_REPORT_DEST}")

    # 2. Update FINAL_NATIVE_CHROMADB_BGE_REPORT.json
    bge_report = json.loads(FINAL_BGE.read_text(encoding="utf-8"))
    bge_report["dossier_collection"] = {
        "backend": dossier.get("backend"),
        "collection_name": dossier.get("collection"),
        "chunk_count": dossier.get("chunk_count"),
        "source_count": dossier.get("source_count"),
        "classification": dossier.get("classification"),
        "requires_human_review": dossier.get("requires_human_review"),
        "experiment_label": dossier.get("experiment_label"),
        "verdict": "PASS" if dossier.get("backend") == "ACTUAL_CHROMADB" and dossier.get("chunk_count", 0) >= 1000 else "FAIL",
    }
    FINAL_BGE.write_text(json.dumps(bge_report, indent=2), encoding="utf-8")
    print(f"Updated {FINAL_BGE.name}")

    # 3. Update FINAL_SOURCE_AND_CITATION_AUDIT.json
    audit = json.loads(FINAL_AUDIT.read_text(encoding="utf-8"))
    audit["dossier_chroma"] = {
        "backend": dossier.get("backend"),
        "collection": dossier.get("collection"),
        "chunk_count": dossier.get("chunk_count"),
        "source_count": dossier.get("source_count"),
        "classification": dossier.get("classification"),
        "requires_human_review": dossier.get("requires_human_review"),
        "verdict": "PASS" if dossier.get("backend") == "ACTUAL_CHROMADB" and dossier.get("chunk_count", 0) >= 1000 else "FAIL",
    }
    verdicts = [v.get("verdict") for v in audit.values() if isinstance(v, dict)]
    audit["overall_verdict"] = "PASS" if all(v == "PASS" for v in verdicts) else "PARTIAL_PASS"
    audit["non_passing"] = [k for k, v in audit.items()
                            if isinstance(v, dict) and v.get("verdict") not in ("PASS", None)]
    FINAL_AUDIT.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(f"Updated {FINAL_AUDIT.name}")

    print("\nAll artefacts updated. Rebuild the release ZIP:")
    print("  python scripts/build_v131_release.py")


if __name__ == "__main__":
    main()
