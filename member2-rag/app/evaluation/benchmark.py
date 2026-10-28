"""Reproducible retrieval benchmark.

Benchmark file (JSONL, one question per line):

    {"question_id": "Q001",
     "question": "...",
     "ctd_section": "3.2.S.4.3",
     "relevant_chunk_ids": ["..."],                     # chunk-level labels
     "relevant_pages": [{"source_identifier": "...", "page_number": 12}],  # page-level labels
     "reference_answer": null,                          # optional, for Ragas
     "expert_notes": "...", "labelled_by": "Member 5"}

Why two kinds of labels?
Chunk IDs change when the chunk size changes, so chunk-level labels cannot be
reused across chunking experiments. Page-level labels ("this page of this
document answers the question") stay valid for every chunking, which makes the
chunk-size comparison fair. Use `relevance_level="page"` for chunking
experiments and `"chunk"` for everything else.

Run configurations (one per experiment arm) are described by `RunConfig`; the
script `scripts/evaluate_retrieval.py` builds one RetrievalService per
config and writes a timestamped JSON result file with all settings.
"""

from __future__ import annotations

import hashlib
import json
import platform
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.evaluation.metrics import (
    hit_at_k,
    latency_summary,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.hashing import normalise_text
from app.retrieval.retrieval_service import RetrievalService
from app.schemas import RetrievedPassage, SearchFilters, normalise_ctd_section


class PageRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_identifier: str = Field(min_length=1)
    page_number: int = Field(ge=1)

    def key(self) -> str:
        return page_key(self.source_identifier, self.page_number)


class BenchmarkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    ctd_section: str
    relevant_chunk_ids: list[str] = Field(default_factory=list)
    relevant_pages: list[PageRef] = Field(default_factory=list)
    reference_answer: str | None = None
    expert_notes: str | None = None
    labelled_by: str | None = None

    @field_validator("ctd_section")
    @classmethod
    def _ctd(cls, v: str) -> str:
        norm = normalise_ctd_section(v)
        if norm is None:
            raise ValueError("ctd_section is required")
        return norm

    @model_validator(mode="after")
    def _labels(self) -> BenchmarkItem:
        if not self.relevant_chunk_ids and not self.relevant_pages:
            raise ValueError("provide relevant_chunk_ids and/or relevant_pages")
        return self

    def relevant_keys(self, level: str) -> set[str]:
        if level == "chunk":
            return set(self.relevant_chunk_ids)
        return {p.key() for p in self.relevant_pages}


class RunConfig(BaseModel):
    """One experiment arm."""

    model_config = ConfigDict(extra="forbid")

    name: str
    collection_name: str
    embedding_model: str = "BAAI/bge-large-en-v1.5"
    use_reranker: bool = True
    reranker_model: str = "BAAI/bge-reranker-base"
    use_section_filter: bool = True
    candidate_k: int = Field(default=20, ge=1)
    final_k: int = Field(default=10, ge=1)
    relevance_level: Literal["chunk", "page"] = "chunk"
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    notes: str | None = None


def page_key(source_identifier: str, page_number: int | None) -> str:
    return f"{source_identifier}|p{page_number if page_number is not None else '?'}"


def passage_key(p: RetrievedPassage, level: str) -> str:
    return p.chunk_id if level == "chunk" else page_key(p.metadata.source_identifier, p.metadata.page_number)


def load_benchmark(path: Path | str) -> list[BenchmarkItem]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Benchmark file not found: {path}")
    items: list[BenchmarkItem] = []
    errors: list[str] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8-sig") as handle:
        for n, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                item = BenchmarkItem(**json.loads(line))
            except (json.JSONDecodeError, ValidationError, TypeError) as exc:
                errors.append(f"line {n}: {exc}")
                continue
            if item.question_id in seen:
                errors.append(f"line {n}: duplicate question_id {item.question_id}")
                continue
            seen.add(item.question_id)
            items.append(item)
    if errors:
        raise ValueError("Invalid benchmark file:\n" + "\n".join(errors))
    if not items:
        raise ValueError(f"Benchmark file is empty: {path}")
    return items


def file_sha256(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def label_and_leakage_checks(service: RetrievalService, items: Sequence[BenchmarkItem]) -> dict:
    """Sanity checks run before every benchmark.

    * Labelled chunk IDs that are not in the index (stale labels).
    * Questions copied verbatim into indexed passages (data leakage: the
      benchmark would then measure string matching, not retrieval).
    """
    all_ids = set(service.store.all_ids())
    missing = sorted({cid for it in items for cid in it.relevant_chunk_ids if cid not in all_ids})
    leaked: list[str] = []
    if all_ids:
        texts = [normalise_text(p.text).lower() for p in service.store.get(sorted(all_ids))]
        for it in items:
            q = normalise_text(it.question).lower()
            if len(q) >= 20 and any(q in t for t in texts):
                leaked.append(it.question_id)
    return {"missing_labelled_chunk_ids": missing, "questions_found_verbatim_in_index": leaked}


@dataclass
class QueryOutcome:
    question_id: str
    retrieved: list[str]
    relevant: list[str]
    latency_ms: float
    metrics: dict[str, float]
    contexts: list[str]


def run_config(
    service: RetrievalService,
    items: Sequence[BenchmarkItem],
    config: RunConfig,
    ks: Sequence[int] = (1, 3, 5, 10),
) -> dict:
    """Evaluate one configuration; returns aggregate + per-query results."""
    if config.final_k > config.candidate_k:
        raise ValueError(f"{config.name}: final_k cannot exceed candidate_k")
    if config.use_reranker and service.reranker is None:
        raise ValueError(f"{config.name}: reranker requested but service has none")
    ks = sorted({k for k in ks if k <= config.final_k}) or [config.final_k]
    outcomes: list[QueryOutcome] = []
    skipped: list[str] = []


    if items:
        service.retrieve(items[0].question, candidate_k=config.candidate_k, final_k=config.final_k,
                         use_reranker=config.use_reranker)

    for item in items:
        relevant = item.relevant_keys(config.relevance_level)
        if not relevant:
            skipped.append(item.question_id)
            continue
        filters = SearchFilters(ctd_sections=[item.ctd_section]) if config.use_section_filter else None
        result = service.retrieve(
            item.question,
            filters=filters,
            candidate_k=config.candidate_k,
            final_k=config.final_k,
            use_reranker=config.use_reranker,
        )
        retrieved = [passage_key(p, config.relevance_level) for p in result.passages]
        m: dict[str, float] = {"rr": reciprocal_rank(retrieved, relevant)}
        for k in ks:
            m[f"recall@{k}"] = recall_at_k(retrieved, relevant, k)
            m[f"precision@{k}"] = precision_at_k(retrieved, relevant, k)
            m[f"hit@{k}"] = hit_at_k(retrieved, relevant, k)
            m[f"ndcg@{k}"] = ndcg_at_k(retrieved, relevant, k)
        outcomes.append(
            QueryOutcome(item.question_id, retrieved, sorted(relevant), result.latency_ms, m,
                         [p.text for p in result.passages])
        )

    aggregate: dict[str, float] = {}
    if outcomes:
        for key in outcomes[0].metrics:
            if key == "rr":
                continue
            aggregate[key] = round(sum(o.metrics[key] for o in outcomes) / len(outcomes), 4)
        aggregate["mrr"] = round(mean_reciprocal_rank([o.metrics["rr"] for o in outcomes]), 4)
    return {
        "config": config.model_dump(),
        "queries_evaluated": len(outcomes),
        "queries_skipped_no_labels_at_level": skipped,
        "aggregate": aggregate,
        "latency": latency_summary([o.latency_ms for o in outcomes]),
        "per_query": [
            {
                "question_id": o.question_id,
                "retrieved": o.retrieved,
                "relevant": o.relevant,
                "latency_ms": o.latency_ms,
                "metrics": {k: round(v, 4) for k, v in o.metrics.items()},
            }
            for o in outcomes
        ],
        "_contexts": {o.question_id: o.contexts for o in outcomes},
    }


def _package_versions() -> dict[str, str]:
    out = {}
    for pkg in ("chromadb", "sentence-transformers", "torch", "transformers", "pydantic", "ragas"):
        try:
            out[pkg] = importlib_metadata.version(pkg)
        except importlib_metadata.PackageNotFoundError:
            out[pkg] = "not installed"
    return out


def run_benchmark(
    benchmark_path: Path | str,
    configs: Sequence[RunConfig],
    service_factory: Callable[[RunConfig], RetrievalService],
    ks: Sequence[int] = (1, 3, 5, 10),
) -> dict:
    """Run every configuration and return a JSON-serialisable report."""
    items = load_benchmark(benchmark_path)
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "benchmark_file": str(benchmark_path),
        "benchmark_sha256": file_sha256(benchmark_path),
        "num_questions": len(items),
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "packages": _package_versions()},
        "runs": [],
    }
    for config in configs:
        service = service_factory(config)
        run = run_config(service, items, config, ks)
        run["knowledge_base_size"] = service.store.count()
        run["checks"] = label_and_leakage_checks(service, items)
        report["runs"].append(run)
    return report


def save_report(report: dict, output_dir: Path | str) -> Path:
    """Write the report (without raw passage contexts) to a timestamped file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    clean = json.loads(json.dumps(report, default=str))
    for run in clean.get("runs", []):
        run.pop("_contexts", None)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"retrieval_benchmark_{stamp}.json"
    path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    return path
