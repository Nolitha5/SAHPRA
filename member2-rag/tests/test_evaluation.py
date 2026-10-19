"""Metrics, benchmark runner and Ragas row building (no real models)."""

from __future__ import annotations

import json

import pytest

from app.evaluation.benchmark import (
    BenchmarkItem,
    RunConfig,
    label_and_leakage_checks,
    load_benchmark,
    run_benchmark,
    save_report,
)
from app.evaluation.metrics import (
    hit_at_k,
    latency_summary,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from app.evaluation.ragas_eval import build_ragas_rows


def test_metric_values():
    retrieved = ["a", "b", "c", "d"]
    relevant = {"b", "d", "z"}
    assert recall_at_k(retrieved, relevant, 2) == pytest.approx(1 / 3)
    assert precision_at_k(retrieved, relevant, 2) == pytest.approx(0.5)
    assert precision_at_k(["b"], relevant, 5) == pytest.approx(0.2)  # fewer results not rewarded
    assert hit_at_k(retrieved, relevant, 1) == 0.0
    assert reciprocal_rank(retrieved, relevant) == pytest.approx(0.5)
    assert reciprocal_rank([], relevant) == 0.0
    assert ndcg_at_k(["b", "x"], {"b"}, 2) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        recall_at_k(retrieved, set(), 3)


def test_latency_summary():
    s = latency_summary([10, 20, 30, 40])
    assert s["p50_ms"] == 25 and s["max_ms"] == 40
    assert latency_summary([])["mean_ms"] == 0.0


def test_benchmark_item_needs_labels():
    with pytest.raises(ValueError):
        BenchmarkItem(question_id="Q", question="q", ctd_section="3.2.S.4")


def test_load_benchmark_errors(tmp_path):
    p = tmp_path / "b.jsonl"
    p.write_text('{"question_id":"Q1","question":"q","ctd_section":"3.2.S.4","relevant_chunk_ids":["a"]}\n'
                 '{"question_id":"Q1","question":"q","ctd_section":"3.2.S.4","relevant_chunk_ids":["a"]}\n')
    with pytest.raises(ValueError, match="duplicate"):
        load_benchmark(p)


def test_shipped_benchmark_template_is_valid():
    from pathlib import Path

    items = load_benchmark(Path(__file__).parent.parent / "benchmarks" / "benchmark.jsonl")
    assert all(i.relevant_chunk_ids and i.relevant_pages for i in items)


def _bench_file(tmp_path):
    rows = [
        {"question_id": "Q1", "question": "validation of analytical procedures", "ctd_section": "3.2.S.4.3",
         "relevant_chunk_ids": ["syn-val-1"],
         "relevant_pages": [{"source_identifier": "SYNTH-GL-A", "page_number": 2}]},
        {"question_id": "Q2", "question": "batch analyses representative batches", "ctd_section": "3.2.S.4.4",
         "relevant_chunk_ids": ["syn-batch-1"]},
    ]
    p = tmp_path / "bench.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows))
    return p


def test_run_benchmark_configs(tmp_path, service):
    path = _bench_file(tmp_path)
    configs = [
        RunConfig(name="dense", collection_name="test_kb", use_reranker=False, candidate_k=5, final_k=3),
        RunConfig(name="rerank", collection_name="test_kb", use_reranker=True, candidate_k=5, final_k=3),
        RunConfig(name="nofilter", collection_name="test_kb", use_section_filter=False, candidate_k=5, final_k=3),
        RunConfig(name="page", collection_name="test_kb", relevance_level="page", candidate_k=5, final_k=3),
    ]
    report = run_benchmark(path, configs, lambda cfg: service, ks=(1, 3))
    assert report["num_questions"] == 2 and len(report["runs"]) == 4
    rerank_run = report["runs"][1]
    assert rerank_run["aggregate"]["mrr"] == 1.0
    assert rerank_run["aggregate"]["recall@1"] == 1.0
    assert rerank_run["checks"]["missing_labelled_chunk_ids"] == []
    assert report["runs"][3]["queries_evaluated"] == 1  # Q2 has no page labels
    assert report["runs"][3]["queries_skipped_no_labels_at_level"] == ["Q2"]
    out = save_report(report, tmp_path / "results")
    saved = json.loads(out.read_text())
    assert "_contexts" not in saved["runs"][0] and saved["benchmark_sha256"]


def test_leakage_and_stale_label_checks(service):
    items = [
        BenchmarkItem(question_id="L1", question="validation of analytical procedures covers specificity",
                      ctd_section="3.2.S.4.3", relevant_chunk_ids=["syn-val-1", "ghost-chunk"]),
    ]
    checks = label_and_leakage_checks(service, items)
    assert checks["missing_labelled_chunk_ids"] == ["ghost-chunk"]
    assert checks["questions_found_verbatim_in_index"] == ["L1"]


def test_ragas_rows(service):
    items = [BenchmarkItem(question_id="Q1", question="q", ctd_section="3.2.S.4", relevant_chunk_ids=["syn-val-1"])]
    rows = build_ragas_rows(service, items, {"Q1": ["ctx"]})
    assert rows[0]["retrieved_contexts"] == ["ctx"]
    assert "validation" in rows[0]["reference_contexts"][0]
