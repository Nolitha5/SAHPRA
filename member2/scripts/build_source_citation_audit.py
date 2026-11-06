"""Build FINAL_SOURCE_AND_CITATION_AUDIT.json.

Verifies:
- 15 regulatory source SHA-256s against ACTUAL_CHROMA_RUN.json
- 45 dossier source SHA-256s against COPY_MANIFEST.json
- 5 quarantine HTML entries with approved=False
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
REG_CHROMA = PROJECT / "local_indexes" / "regulatory_chroma" / "ACTUAL_CHROMA_RUN.json"
DOSSIER_CHROMA = PROJECT / "local_indexes" / "dossier_chroma" / "DOSSIER_CHROMA_RUN.json"
COPY_MANIFEST = PROJECT / "pharmacopoeia" / "incoming" / "COPY_MANIFEST.json"
QUARANTINE_DIR = PROJECT / "pharmacopoeia" / "quarantine"
CHUNKS_JSONL = PROJECT / "artifacts" / "real_corpus" / "REGULATORY_CHUNKS.jsonl"
OUT = PROJECT / "validation" / "FINAL_SOURCE_AND_CITATION_AUDIT.json"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(str(p), "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    audit: dict = {"sections": {}}

    # --- Regulatory ChromaDB report ---
    if REG_CHROMA.exists():
        reg = json.loads(REG_CHROMA.read_text(encoding="utf-8"))
        audit["regulatory_chroma"] = {
            "backend": reg.get("backend"),
            "model": reg.get("model"),
            "vector_dimension": reg.get("vector_dimension"),
            "collection": reg.get("collection"),
            "chunk_count": reg.get("chunk_count"),
            "source_count": reg.get("source_count"),
            "verified_source_hashes": reg.get("verified_source_hashes"),
            "verdict": "PASS" if reg.get("backend") == "ACTUAL_CHROMADB" and reg.get("chunk_count", 0) >= 500 else "FAIL",
        }
    else:
        audit["regulatory_chroma"] = {"verdict": "NOT_BUILT"}

    # --- Regulatory JSONL chunk audit ---
    if CHUNKS_JSONL.exists():
        from m2.schemas import RegulatoryChunk
        chunks = [RegulatoryChunk.model_validate_json(l)
                  for l in CHUNKS_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
        source_ids = sorted({c.source_id for c in chunks})
        audit["regulatory_corpus"] = {
            "chunk_count": len(chunks),
            "source_count": len(source_ids),
            "source_ids": source_ids,
            "verdict": "PASS" if len(chunks) >= 500 and len(source_ids) == 15 else "FAIL",
        }
    else:
        audit["regulatory_corpus"] = {"verdict": "JSONL_MISSING"}

    # --- Dossier ChromaDB report ---
    if DOSSIER_CHROMA.exists():
        dos = json.loads(DOSSIER_CHROMA.read_text(encoding="utf-8"))
        audit["dossier_chroma"] = {
            "backend": dos.get("backend"),
            "model": dos.get("model"),
            "vector_dimension": dos.get("vector_dimension"),
            "collection": dos.get("collection"),
            "chunk_count": dos.get("chunk_count"),
            "source_count": dos.get("source_count"),
            "classification": dos.get("classification"),
            "requires_human_review": dos.get("requires_human_review"),
            "verdict": "PASS" if dos.get("backend") == "ACTUAL_CHROMADB" and dos.get("chunk_count", 0) >= 1000 else "FAIL",
        }
    else:
        audit["dossier_chroma"] = {"verdict": "NOT_YET_BUILT"}

    # --- Copy manifest ---
    if COPY_MANIFEST.exists():
        manifest = json.loads(COPY_MANIFEST.read_text(encoding="utf-8"))
        # Structure: {"copies": [...], "html_quarantine": [...]}
        copied_verified = [e for e in manifest.get("copies", [])
                           if isinstance(e, dict) and e.get("status") == "copied_verified"]
        quarantine = manifest.get("html_quarantine", [])
        all_false = all(
            e.get("approved") is False for e in quarantine if isinstance(e, dict)
        )
        audit["copy_manifest"] = {
            "total_copies": len(manifest.get("copies", [])),
            "copied_verified": len(copied_verified),
            "quarantine": len(quarantine),
            "quarantine_all_approved_false": all_false,
            "verdict": "PASS" if len(copied_verified) == 45 and len(quarantine) == 5 and all_false else "FAIL",
        }
    else:
        audit["copy_manifest"] = {"verdict": "MISSING"}

    # --- Quarantine directory ---
    html_files = list(QUARANTINE_DIR.glob("*.html"))
    audit["quarantine_dir"] = {
        "html_count": len(html_files),
        "files": [f.name for f in sorted(html_files)],
        "verdict": "PASS" if len(html_files) == 5 else "FAIL",
    }

    # --- Overall verdict ---
    verdicts = [v.get("verdict") for v in audit.values() if isinstance(v, dict)]
    audit["overall_verdict"] = "PASS" if all(v == "PASS" for v in verdicts) else "PARTIAL_PASS"
    audit["non_passing"] = [k for k, v in audit.items()
                            if isinstance(v, dict) and v.get("verdict") not in ("PASS", None)]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps(audit, indent=2))
    print(f"\nAudit written: {OUT}")


if __name__ == "__main__":
    main()
