"""Retrieval experiments: BM25 vs BGE for Valsartan, Amlodipine, HCTZ.

Computes Precision@K, Recall@K, MRR, nDCG for both retrieval methods
against researcher-authored navigation probes. Saves results to
validation/RETRIEVAL_EXPERIMENTS_v1_3.json.

DISCLAIMER: Probes are researcher-authored. No expert-validated ground truth.
Results cannot be cited as regulatory-quality performance.
"""
from __future__ import annotations
import json, math
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
PROBES_FILE = PROJECT / "examples" / "researcher_navigation_probes_v0.6.json"
REG_CHROMA_REPORT = PROJECT / "local_indexes" / "regulatory_chroma" / "ACTUAL_CHROMA_RUN.json"
DOSSIER_CHROMA_REPORT = PROJECT / "local_indexes" / "dossier_chroma" / "DOSSIER_CHROMA_RUN.json"
OUT = PROJECT / "validation" / "RETRIEVAL_EXPERIMENTS_v1_3.json"

SUBSTANCE_QUERIES = {
    "valsartan": [
        "Valsartan specification analytical procedure ICH Q6A",
        "Valsartan impurities limit qualification ICH Q3A",
        "Valsartan batch analysis specification compliance",
        "Valsartan validation analytical method accuracy precision",
        "Valsartan stability degradation products ICH Q1A",
    ],
    "amlodipine": [
        "Amlodipine besylate specification analytical procedure",
        "Amlodipine batch analyses control drug substance",
        "Amlodipine stability data ICH Q1A",
        "Amlodipine validation analytical procedures",
        "Amlodipine impurities qualification threshold",
    ],
    "hydrochlorothiazide": [
        "Hydrochlorothiazide HCTZ specification ICH Q6A",
        "Hydrochlorothiazide analytical procedure validation",
        "HCTZ batch analysis control drug substance",
        "Hydrochlorothiazide impurities characterisation",
        "HCTZ stability ICH Q1A degradation",
    ],
}

K_VALUES = [1, 3, 5, 10]


def precision_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    top_k = retrieved_ids[:k]
    return sum(1 for r in top_k if r in relevant_ids) / k


def recall_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top_k = retrieved_ids[:k]
    return sum(1 for r in top_k if r in relevant_ids) / len(relevant_ids)


def mrr(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    for rank, rid in enumerate(retrieved_ids, 1):
        if rid in relevant_ids:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: set[str], k: int) -> float:
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, rid in enumerate(retrieved_ids[:k], 1)
        if rid in relevant_ids
    )
    ideal_hits = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def run_bm25_experiment(probes: list[dict]) -> dict:
    from m2.retrieval import lexical_bm25
    from m2.schemas import RegulatoryChunk

    chunks_path = PROJECT / "artifacts" / "real_corpus" / "REGULATORY_CHUNKS.jsonl"
    chunks = [RegulatoryChunk.model_validate_json(line)
              for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # Build source_id -> chunk_ids mapping for relevance expansion
    src_to_chunks: dict[str, list[str]] = {}
    for c in chunks:
        src_to_chunks.setdefault(c.source_id, []).append(c.chunk_id)

    results = {}
    for probe in probes:
        query = probe["query"]
        # Expand expected source IDs to chunk IDs
        expected_sources = set(probe.get("expected_source_ids", []))
        expected_chunks: set[str] = set()
        for src in expected_sources:
            # Match source_id that contains the expected source identifier
            for sid, cids in src_to_chunks.items():
                if src in sid or sid.startswith(src.replace("-", "_")):
                    expected_chunks.update(cids)
        try:
            scores = lexical_bm25(query, chunks)
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            # Map chunk_ids back to source_ids for consistent relevance matching
            chunk_id_to_src = {c.chunk_id: c.source_id for c in chunks}
            retrieved = [chunk_id_to_src.get(cid, cid) for cid, _ in ranked[:10]]
        except Exception:
            retrieved = []
        results[query] = {"retrieved": retrieved, "expected": expected_sources}
    return results


def run_bge_experiment(probes: list[dict], chroma_dir: str, collection_prefix: str) -> dict:
    from m2.embeddings import SentenceTransformerEmbedder
    from m2.storage import ChromaVectorStore

    embedder = SentenceTransformerEmbedder("BAAI/bge-large-en-v1.5")
    store = ChromaVectorStore(embedder, chroma_dir, collection_prefix=collection_prefix)

    results = {}
    for probe in probes:
        query = probe["query"]
        expected = set(probe.get("expected_source_ids", []))
        try:
            hits = store.search(query, limit=10)
            retrieved = [chunk.chunk_id for chunk, _ in hits]
        except Exception as e:
            retrieved = []
        results[query] = {"retrieved": retrieved, "expected": expected}
    return results


def compute_metrics(results: dict, k_values: list[int]) -> dict:
    all_p = {k: [] for k in k_values}
    all_r = {k: [] for k in k_values}
    all_mrr = []
    all_ndcg = {k: [] for k in k_values}

    for query, data in results.items():
        retrieved = data["retrieved"]
        relevant = data["expected"]
        if not relevant:
            continue
        for k in k_values:
            all_p[k].append(precision_at_k(retrieved, relevant, k))
            all_r[k].append(recall_at_k(retrieved, relevant, k))
            all_ndcg[k].append(ndcg_at_k(retrieved, relevant, k))
        all_mrr.append(mrr(retrieved, relevant))

    n = len(all_mrr) if all_mrr else 1
    metrics = {"query_count": n, "MRR": round(sum(all_mrr) / n, 4) if all_mrr else None}
    for k in k_values:
        metrics[f"P@{k}"] = round(sum(all_p[k]) / len(all_p[k]), 4) if all_p[k] else None
        metrics[f"R@{k}"] = round(sum(all_r[k]) / len(all_r[k]), 4) if all_r[k] else None
        metrics[f"nDCG@{k}"] = round(sum(all_ndcg[k]) / len(all_ndcg[k]), 4) if all_ndcg[k] else None
    return metrics


def substance_smoke_queries(store_fn) -> dict:
    """Run substance-specific queries, return hit counts."""
    smoke = {}
    for substance, queries in SUBSTANCE_QUERIES.items():
        hits = []
        for q in queries:
            try:
                results = store_fn(q)
                hits.append(len(results))
            except Exception:
                hits.append(0)
        smoke[substance] = {"queries": queries, "hit_counts": hits,
                            "avg_hits": sum(hits) / len(hits)}
    return smoke


def main() -> None:
    if not PROBES_FILE.exists():
        print(f"ERROR: Probes file not found: {PROBES_FILE}")
        return

    suite = json.loads(PROBES_FILE.read_text(encoding="utf-8"))
    probes_raw = suite.get("probes", suite.get("queries", suite)) if isinstance(suite, dict) else suite
    # Normalise to {query, expected_source_ids} format
    probes = []
    for p in probes_raw:
        if isinstance(p, str):
            probes.append({"query": p, "expected_source_ids": []})
        else:
            q = p.get("question") or p.get("query", "")
            # expected_source_id (singular) or expected_source_ids (list)
            src = p.get("expected_source_ids") or (
                [p["expected_source_id"]] if p.get("expected_source_id") else []
            )
            probes.append({"query": q, "expected_source_ids": src})
    print(f"Loaded {len(probes)} probes from {PROBES_FILE.name}")

    reg_chroma_dir = str(PROJECT / "local_indexes" / "regulatory_chroma")
    reg_chroma_ready = (PROJECT / "local_indexes" / "regulatory_chroma" / "ACTUAL_CHROMA_RUN.json").exists()
    dossier_chroma_dir = str(PROJECT / "local_indexes" / "dossier_chroma")
    dossier_chroma_ready = (PROJECT / "local_indexes" / "dossier_chroma" / "DOSSIER_CHROMA_RUN.json").exists()

    report = {
        "disclaimer": "Researcher-authored probes only. Not expert-validated ground truth.",
        "probe_count": len(probes),
        "k_values": K_VALUES,
    }

    # BM25 experiment
    print("\nRunning BM25 experiment...")
    bm25_results = run_bm25_experiment(probes)
    bm25_metrics = compute_metrics(bm25_results, K_VALUES)
    report["bm25"] = bm25_metrics
    print(f"  BM25 metrics: {bm25_metrics}")

    # BGE regulatory experiment
    if reg_chroma_ready:
        print("\nRunning BGE regulatory corpus experiment...")
        from m2.storage import ChromaVectorStore
        from m2.embeddings import SentenceTransformerEmbedder
        embedder = SentenceTransformerEmbedder("BAAI/bge-large-en-v1.5")
        reg_store = ChromaVectorStore(embedder, reg_chroma_dir,
                                      collection_prefix="regulatory_technical_unapproved")
        bge_results = {}
        for probe in probes:
            query = probe["query"]
            expected_sources = set(probe.get("expected_source_ids", []))
            try:
                hits = reg_store.search(query, limit=10)
                # Use source_id for relevance matching (matches probe expected_source_id)
                retrieved = [chunk.source_id for chunk, _ in hits]
            except Exception:
                retrieved = []
            bge_results[query] = {"retrieved": retrieved, "expected": expected_sources}
        bge_metrics = compute_metrics(bge_results, K_VALUES)
        report["bge_regulatory"] = bge_metrics
        print(f"  BGE regulatory metrics: {bge_metrics}")

        # Substance smoke queries on regulatory corpus
        def reg_search(q):
            hits = reg_store.search(q, limit=5)
            return [c for c, _ in hits]
        report["bge_regulatory_substance_smoke"] = substance_smoke_queries(reg_search)
    else:
        report["bge_regulatory"] = {"status": "SKIPPED — regulatory ChromaDB not yet built"}

    # BGE dossier experiment (smoke only — no gold labels for dossier)
    if dossier_chroma_ready:
        print("\nRunning BGE dossier corpus smoke queries...")
        from m2.storage import ChromaVectorStore
        from m2.embeddings import SentenceTransformerEmbedder
        embedder2 = SentenceTransformerEmbedder("BAAI/bge-large-en-v1.5")
        dos_store = ChromaVectorStore(embedder2, dossier_chroma_dir,
                                      collection_prefix="sponsor_dossier_unverified")

        def dos_search(q):
            hits = dos_store.search(q, limit=5)
            return [c for c, _ in hits]
        report["bge_dossier_substance_smoke"] = substance_smoke_queries(dos_search)
    else:
        report["bge_dossier_substance_smoke"] = {"status": "SKIPPED — dossier ChromaDB not yet built"}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written: {OUT}")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("bge_regulatory_substance_smoke", "bge_dossier_substance_smoke")},
                     indent=2))


if __name__ == "__main__":
    main()
