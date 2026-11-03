"""Retrieval metrics (pure functions, no dependencies).

Definitions for one query with a ranked list `retrieved` and a set of
relevant items `relevant`:

* Recall@K    = |relevant ∩ top-K| / |relevant|
* Precision@K = |relevant ∩ top-K| / K
                (K is the cut-off, even if fewer than K items came back - the
                 standard IR definition, so returning fewer items is not rewarded)
* Hit@K       = 1 if any relevant item is in the top-K, else 0
* RR          = 1 / rank of the first relevant item (0 if none)
* nDCG@K      = binary-relevance normalised discounted cumulative gain

Items are compared as strings; the benchmark decides whether those strings
are chunk IDs or "source|page" keys (see benchmark.py).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import mean, median


def _top(retrieved: Sequence[str], k: int) -> list[str]:
    if k < 1:
        raise ValueError("k must be >= 1")
    # Deduplicate while keeping order (page-level keys can repeat).
    seen: list[str] = []
    for item in retrieved:
        if item not in seen:
            seen.append(item)
    return seen[:k]


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant:
        raise ValueError("relevant set must not be empty")
    return len(set(_top(retrieved, k)) & relevant) / len(relevant)


def precision_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    return len(set(_top(retrieved, k)) & relevant) / k


def hit_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    return 1.0 if set(_top(retrieved, k)) & relevant else 0.0


def reciprocal_rank(retrieved: Sequence[str], relevant: set[str]) -> float:
    for rank, item in enumerate(_top(retrieved, max(len(retrieved), 1)), start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    top = _top(retrieved, k)
    dcg = sum(1.0 / math.log2(i + 2) for i, item in enumerate(top) if item in relevant)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal else 0.0


def mean_reciprocal_rank(rr_values: Sequence[float]) -> float:
    return mean(rr_values) if rr_values else 0.0


def latency_summary(latencies_ms: Sequence[float]) -> dict[str, float]:
    if not latencies_ms:
        return {"mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    ordered = sorted(latencies_ms)
    p95_index = min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "mean_ms": round(mean(ordered), 2),
        "p50_ms": round(median(ordered), 2),
        "p95_ms": round(ordered[p95_index], 2),
        "max_ms": round(ordered[-1], 2),
    }
