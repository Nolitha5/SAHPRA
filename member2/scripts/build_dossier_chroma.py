"""Build a ChromaDB collection from the copied CTD sponsor dossier PDFs.

These are Class D (sponsor dossier) documents — unverified, not approved as
regulatory authority. The collection is labelled SPONSOR_DOSSIER_UNVERIFIED.
Human review is required before any result is used in a regulatory assessment.
"""
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(str(p), "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text using pypdf (already a project dependency)."""
    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
        return "\n".join(pages)
    except Exception as e:
        return f"[TEXT EXTRACTION FAILED: {e}]"


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 128) -> list[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i : i + chunk_size]
        chunks.append(" ".join(chunk_words))
        i += chunk_size - overlap
        if i >= len(words):
            break
    return [c for c in chunks if len(c.strip()) > 50]


def infer_ctd_section(filename: str) -> str:
    nl = filename.lower()
    mapping = {
        "analytical-procedure": "3.2.S.4.2",
        "analytical methods": "3.2.S.4.2",
        "batch-analy": "3.2.S.4.4",
        "justification-of-specification": "3.2.S.4.5",
        "specification": "3.2.S.4.1",
        "validation-analyt": "3.2.S.4.3",
        "reference-standard": "3.2.S.5",
        "stability-data": "3.2.S.7",
        "stability-summary": "3.2.S.7",
        "postapproval-stability": "3.2.S.7",
        "impurities": "3.2.S.3",
        "elucidation-of-structure": "3.2.S.3",
        "general-properties": "3.2.S.3",
        "nomenclature": "3.2.S.1",
        "container-closure": "3.2.S.6",
        "manufacture": "3.2.S.2",
    }
    return next((v for k, v in mapping.items() if k in nl), "")


def infer_substance(folder_name: str) -> str:
    n = folder_name.lower()
    if "valsartan" in n:
        return "valsartan"
    if "amlodipine" in n:
        return "amlodipine"
    if "hctz" in n or "hydrochlorothiazide" in n:
        return "hydrochlorothiazide"
    return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path,
                        default=PROJECT / "pharmacopoeia/incoming/raw_from_pharmacy")
    parser.add_argument("--chroma-dir", type=Path,
                        default=PROJECT / "local_indexes/dossier_chroma")
    parser.add_argument("--model", default="BAAI/bge-large-en-v1.5")
    parser.add_argument("--chunk-size", type=int, default=512)
    parser.add_argument("--overlap", type=int, default=128)
    args = parser.parse_args()

    if not args.source_dir.exists():
        raise RuntimeError(f"Source directory not found: {args.source_dir}")

    from m2.embeddings import SentenceTransformerEmbedder
    from m2.storage import ChromaVectorStore
    from m2.schemas import RegulatoryChunk

    embedder = SentenceTransformerEmbedder(args.model)
    args.chroma_dir.mkdir(parents=True, exist_ok=True)
    store = ChromaVectorStore(embedder, str(args.chroma_dir),
                              collection_prefix="sponsor_dossier_unverified")

    all_chunks: list[RegulatoryChunk] = []
    source_log = []

    for substance_dir in sorted(args.source_dir.iterdir()):
        if not substance_dir.is_dir():
            continue
        substance = infer_substance(substance_dir.name)
        print(f"\nProcessing {substance_dir.name} ({substance})...")

        for pdf in sorted(substance_dir.glob("*.pdf")):
            src_sha = sha256_file(pdf)
            ctd = infer_ctd_section(pdf.name)
            print(f"  Extracting {pdf.name}...")
            text = extract_text_from_pdf(pdf)
            raw_chunks = chunk_text(text, args.chunk_size, args.overlap)

            for idx, chunk_text_val in enumerate(raw_chunks):
                chunk_id = hashlib.sha256(
                    f"{src_sha}::{idx}".encode()
                ).hexdigest()[:32]
                chunk = RegulatoryChunk(
                    chunk_id=chunk_id,
                    source_id=f"dossier_{substance}_{pdf.stem}",
                    text=chunk_text_val,
                    section=ctd or "UNKNOWN",
                    page=idx + 1,
                    chunk_kind="dossier",
                    checksum=src_sha[:16],
                    metadata={
                        "substance": substance,
                        "ctd_section": ctd or "UNKNOWN",
                        "classification": "D_SPONSOR_DOSSIER",
                        "source_sha256": src_sha,
                        "approved": False,
                        "requires_human_review": True,
                    },
                )
                all_chunks.append(chunk)

            source_log.append({
                "file": pdf.name,
                "substance": substance,
                "ctd_section": ctd,
                "sha256": src_sha,
                "chunks": len(raw_chunks),
                "classification": "D_SPONSOR_DOSSIER",
                "approved": False,
                "provenance_verified": False,
                "warning": "Sponsor dossier — unverified identity; requires human review before regulatory use",
            })
            print(f"    {len(raw_chunks)} chunks")

    print(f"\nUpserting {len(all_chunks)} chunks into ChromaDB (batch=25)...")
    import time
    BATCH = 25
    for start in range(0, len(all_chunks), BATCH):
        subset = all_chunks[start : start + BATCH]
        vectors = embedder.embed([c.text for c in subset])
        store.collection.upsert(
            ids=[c.chunk_id for c in subset],
            embeddings=vectors,
            documents=[c.text for c in subset],
            metadatas=[
                {
                    "source_id": c.source_id,
                    "section": c.section,
                    "serialized_chunk": c.model_dump_json(),
                }
                for c in subset
            ],
        )
        if (start // BATCH) % 10 == 9:
            print(f"  {start + BATCH}/{len(all_chunks)} chunks upserted…")
            time.sleep(0.5)
    print(f"  {len(all_chunks)}/{len(all_chunks)} chunks upserted.")
    actual_count = store.count()
    if actual_count < len(all_chunks) * 0.95:
        raise RuntimeError(f"Upsert incomplete: {actual_count}/{len(all_chunks)}")

    # Smoke test
    test_queries = [
        "analytical procedure validation valsartan",
        "batch analysis specification hydrochlorothiazide",
        "amlodipine stability data impurities",
    ]
    smoke_results = []
    for q in test_queries:
        results = store.search(q, limit=3)
        smoke_results.append({
            "query": q,
            "hits": len(results),
            "top_chunk_id": results[0][0].chunk_id if results else None,
        })

    report = {
        "backend": "ACTUAL_CHROMADB",
        "model": embedder.name,
        "vector_dimension": embedder.dimension,
        "collection": store.collection_name,
        "chunk_count": actual_count,
        "source_count": len(source_log),
        "classification": "D_SPONSOR_DOSSIER",
        "regulatory_source_approval": False,
        "requires_human_review": True,
        "smoke_tests": smoke_results,
        "sources": source_log,
        "experiment_label": "DOSSIER_CORPUS_TECHNICAL_ONLY_NO_GROUND_TRUTH",
    }
    out = args.chroma_dir / "DOSSIER_CHROMA_RUN.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "sources"}, indent=2))
    print(f"\nFull report: {out}")


if __name__ == "__main__":
    main()
