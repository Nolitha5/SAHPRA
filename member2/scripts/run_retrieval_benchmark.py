"""Corrected retrieval benchmark for SAHPRA Member 2 v1.3.

Evaluates BM25 and BGE on 30 researcher-authored document-navigation probes.

IMPORTANT NOTES:
- These are researcher-authored technical navigation probes, NOT expert-labelled
  regulatory accuracy assessments.
- Source-level evaluation: relevance is at the SOURCE document level (one relevant
  source per query). Multiple chunks from the same source count as ONE hit.
- Passage-level evaluation is NOT performed here — no passage-level gold labels exist.
- The previous run reported Recall@K > 1.0 because chunks from the same source were
  counted as distinct relevant items. This file corrects that error.
- Results are labelled SUPERSEDED_INVALID for the prior run.

Metrics computed:
  Hit@K        — did the correct source appear in top-K? (binary, per query)
  MRR          — mean reciprocal rank of the first relevant source hit
  source-P@K   — fraction of top-K unique sources that are relevant
  source-R@K   — fraction of relevant sources found in top-K (denominator=1 here)
  source-nDCG@K — normalised DCG treating relevance as source-level binary
"""
from __future__ import annotations
import json, math
from pathlib import Path
from collections import OrderedDict

PROJECT = Path(__file__).resolve().parent.parent
PROBES_FILE = PROJECT / "examples" / "researcher_navigation_probes_v0.6.json"
REG_CHROMA_REPORT = PROJECT / "local_indexes" / "regulatory_chroma" / "ACTUAL_CHROMA_RUN.json"
OUT = PROJECT / "validation" / "FINAL_RETRIEVAL_BENCHMARK.json"


# ---------------------------------------------------------------------------
# Source-level metric helpers
# ---------------------------------------------------------------------------

def hit_at_k(ranked_sources: list[str], relevant: set[str], k: int) -> float:
    """1 if any relevant source appears in the unique top-K sources, else 0."""
    seen: list[str] = []
    for s in ranked_sources:
        if s not in seen:
            seen.append(s)
        if len(seen) == k:
            break
    return 1.0 if any(s in relevant for s in seen) else 0.0


def mrr_source(ranked_sources: list[str], relevant: set[str]) -> float:
    """Reciprocal rank of first relevant source in the de-duplicated ranking."""
    seen: list[str] = []
    for s in ranked_sources:
        if s not in seen:
            seen.append(s)
            if s in relevant:
                return 1.0 / len(seen)
    return 0.0


def precision_at_k_source(ranked_sources: list[str], relevant: set[str], k: int) -> float:
    """Fraction of unique top-K sources that are relevant."""
    unique_top_k: list[str] = []
    for s in ranked_sources:
        if s not in unique_top_k:
            unique_top_k.append(s)
        if len(unique_top_k) == k:
            break
    if not unique_top_k:
        return 0.0
    return sum(1 for s in unique_top_k if s in relevant) / len(unique_top_k)


def recall_at_k_source(ranked_sources: list[str], relevant: set[str], k: int) -> float:
    """Fraction of relevant sources found in unique top-K (denominator = |relevant|)."""
    if not relevant:
        return 0.0
    unique_top_k: list[str] = []
    for s in ranked_sources:
        if s not in unique_top_k:
            unique_top_k.append(s)
        if len(unique_top_k) == k:
            break
    found = sum(1 for s in unique_top_k if s in relevant)
    return found / len(relevant)


def ndcg_at_k_source(ranked_sources: list[str], relevant: set[str], k: int) -> float:
    """nDCG@K at source level (binary relevance, de-duplicated ranking)."""
    unique_top_k: list[str] = []
    for s in ranked_sources:
        if s not in unique_top_k:
            unique_top_k.append(s)
        if len(unique_top_k) == k:
            break
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, s in enumerate(unique_top_k, 1)
        if s in relevant
    )
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def aggregate_metrics(per_query: list[dict], k_values: list[int]) -> dict:
    n = len(per_query)
    if n == 0:
        return {}
    agg: dict = {"query_count": n}
    agg["MRR"] = round(sum(q["mrr"] for q in per_query) / n, 4)
    for k in k_values:
        agg[f"Hit@{k}"] = round(sum(q[f"hit@{k}"] for q in per_query) / n, 4)
        agg[f"P@{k}"] = round(sum(q[f"p@{k}"] for q in per_query) / n, 4)
        agg[f"R@{k}"] = round(sum(q[f"r@{k}"] for q in per_query) / n, 4)
        agg[f"nDCG@{k}"] = round(sum(q[f"ndcg@{k}"] for q in per_query) / n, 4)
    return agg


# ---------------------------------------------------------------------------
# Load probes
# ---------------------------------------------------------------------------

def load_probes(path: Path) -> list[dict]:
    suite = json.loads(path.read_text(encoding="utf-8"))
    raw = suite.get("probes", suite.get("queries", suite)) if isinstance(suite, dict) else suite
    probes = []
    for p in raw:
        q = p.get("question") or p.get("query", "") if isinstance(p, dict) else p
        src = (p.get("expected_source_ids") or
               ([p["expected_source_id"]] if isinstance(p, dict) and p.get("expected_source_id") else []))
        probes.append({"query": q, "expected_source_ids": src, "raw": p})
    return probes


# ---------------------------------------------------------------------------
# BM25 retrieval (source-deduped ranking)
# ---------------------------------------------------------------------------

def bm25_retrieve(query: str, chunks, top_k: int = 20) -> list[str]:
    """Returns source-level ranking (de-duplicated, ordered by best chunk score)."""
    from m2.retrieval import lexical_bm25
    scores = lexical_bm25(query, chunks)
    # Aggregate to source level: max chunk score per source
    src_scores: dict[str, float] = {}
    chunk_by_id = {c.chunk_id: c for c in chunks}
    for chunk_id, score in scores.items():
        c = chunk_by_id.get(chunk_id)
        if c:
            src_scores[c.source_id] = max(src_scores.get(c.source_id, 0.0), score)
    return [src for src, _ in sorted(src_scores.items(), key=lambda x: x[1], reverse=True)][:top_k]


# ---------------------------------------------------------------------------
# BGE retrieval (source-deduped ranking)
# ---------------------------------------------------------------------------

def bge_retrieve(query: str, store, top_k: int = 20) -> list[str]:
    """Returns source-level ranking from ChromaDB (de-duplicated by source_id)."""
    hits = store.search(query, limit=top_k * 3)  # over-fetch to allow dedup
    seen: list[str] = []
    for chunk, _ in hits:
        if chunk.source_id not in seen:
            seen.append(chunk.source_id)
        if len(seen) == top_k:
            break
    return seen


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    probes = load_probes(PROBES_FILE)
    print(f"Loaded {len(probes)} probes")

    K_VALUES = [1, 3, 5, 10]

    # Load corpus chunks
    from m2.schemas import RegulatoryChunk
    chunks_path = PROJECT / "artifacts" / "real_corpus" / "REGULATORY_CHUNKS.jsonl"
    chunks = [RegulatoryChunk.model_validate_json(line)
              for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"Corpus: {len(chunks)} chunks from {len({c.source_id for c in chunks})} sources")

    report: dict = {
        "label": "researcher_authored_technical_navigation",
        "disclaimer": (
            "30 researcher-authored document-navigation probes. "
            "NOT expert-labelled regulatory accuracy assessment. "
            "Source-level binary relevance: one relevant source per query."
        ),
        "probe_count": len(probes),
        "corpus_chunks": len(chunks),
        "corpus_sources": len({c.source_id for c in chunks}),
        "k_values": K_VALUES,
        "superseded": {
            "note": "Previous RETRIEVAL_EXPERIMENTS_v1_3.json reported Recall@K > 1.0",
            "root_cause": (
                "Multiple chunks from the same source were counted as separate relevant items. "
                "Precision and Recall denominators were chunk-level, not source-level."
            ),
            "status": "SUPERSEDED_INVALID",
        },
        "query_level_results": {},
    }

    # BM25
    print("\nRunning BM25...")
    bm25_per_query = []
    for probe in probes:
        q = probe["query"]
        relevant = set(probe["expected_source_ids"])
        ranked = bm25_retrieve(q, chunks)
        qr: dict = {"query": q, "relevant_sources": list(relevant), "ranked_sources": ranked}
        qr["mrr"] = mrr_source(ranked, relevant)
        for k in K_VALUES:
            qr[f"hit@{k}"] = hit_at_k(ranked, relevant, k)
            qr[f"p@{k}"] = precision_at_k_source(ranked, relevant, k)
            qr[f"r@{k}"] = recall_at_k_source(ranked, relevant, k)
            qr[f"ndcg@{k}"] = ndcg_at_k_source(ranked, relevant, k)
        bm25_per_query.append(qr)
    report["bm25"] = aggregate_metrics(bm25_per_query, K_VALUES)
    report["bm25"]["note"] = "BM25 lexical scoring; source-level deduplication"
    report["query_level_results"]["bm25"] = bm25_per_query
    print(f"  BM25: MRR={report['bm25']['MRR']} Hit@1={report['bm25']['Hit@1']} Hit@5={report['bm25']['Hit@5']}")

    # BGE
    reg_chroma_ready = REG_CHROMA_REPORT.exists()
    if reg_chroma_ready:
        print("\nRunning BGE (regulatory ChromaDB)...")
        from m2.embeddings import SentenceTransformerEmbedder
        from m2.storage import ChromaVectorStore
        embedder = SentenceTransformerEmbedder("BAAI/bge-large-en-v1.5")
        store = ChromaVectorStore(
            embedder,
            str(PROJECT / "local_indexes" / "regulatory_chroma"),
            collection_prefix="regulatory_technical_unapproved",
        )
        bge_per_query = []
        for probe in probes:
            q = probe["query"]
            relevant = set(probe["expected_source_ids"])
            ranked = bge_retrieve(q, store)
            qr = {"query": q, "relevant_sources": list(relevant), "ranked_sources": ranked}
            qr["mrr"] = mrr_source(ranked, relevant)
            for k in K_VALUES:
                qr[f"hit@{k}"] = hit_at_k(ranked, relevant, k)
                qr[f"p@{k}"] = precision_at_k_source(ranked, relevant, k)
                qr[f"r@{k}"] = recall_at_k_source(ranked, relevant, k)
                qr[f"ndcg@{k}"] = ndcg_at_k_source(ranked, relevant, k)
            bge_per_query.append(qr)
        report["bge_regulatory"] = aggregate_metrics(bge_per_query, K_VALUES)
        report["bge_regulatory"]["note"] = "BGE bge-large-en-v1.5; source-level deduplication; regulatory corpus only"
        report["query_level_results"]["bge_regulatory"] = bge_per_query
        print(f"  BGE: MRR={report['bge_regulatory']['MRR']} Hit@1={report['bge_regulatory']['Hit@1']} Hit@5={report['bge_regulatory']['Hit@5']}")
    else:
        report["bge_regulatory"] = {"status": "SKIPPED — regulatory ChromaDB not ready"}

    # Additional comparisons per spec
    report["additional_comparisons"] = {
        "bge_m3": {"status": "NOT_EXECUTED — model weights not downloaded (multilingual; not required for EN corpus)"},
        "bge_reranker_large": {"status": "NOT_EXECUTED — reranker model not downloaded; would require second-stage scoring"},
        "hybrid_bm25_bge": {"status": "NOT_EXECUTED — implementation available in m2.retrieval but not benchmarked in this run"},
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Write full report including query-level raw output
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Print summary (exclude verbose query-level)
    summary = {k: v for k, v in report.items() if k != "query_level_results"}
    print("\n" + json.dumps(summary, indent=2))
    print(f"\nFull report (with per-query raw output): {OUT}")


if __name__ == "__main__":
    main()
