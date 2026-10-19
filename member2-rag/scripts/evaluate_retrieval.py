"""Run the retrieval benchmark for one or more configurations.

Examples (from the member2-rag folder):
    python scripts/evaluate_retrieval.py --benchmark benchmarks/benchmark.jsonl \
        --configs benchmarks/configs.json --output-dir results

    # also compute Ragas non-LLM context metrics (needs requirements-eval.txt)
    python scripts/evaluate_retrieval.py --benchmark benchmarks/benchmark.jsonl \
        --configs benchmarks/configs.json --ragas

Each config needs its own, already-loaded collection (e.g. one collection per
embedding model or per chunk size). A results/retrieval_benchmark_<UTC>.json
file is written with every setting, package version and the benchmark hash so
the run can be reproduced and reported honestly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings
from app.embeddings.bge_embeddings import BGEEmbeddings
from app.evaluation.benchmark import RunConfig, load_benchmark, run_benchmark, save_report
from app.knowledge_base.document_store import ChromaDocumentStore
from app.logging_utils import configure_logging
from app.retrieval.reranker import BGEReranker
from app.retrieval.retrieval_service import RetrievalService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--benchmark", type=Path, default=Path("benchmarks/benchmark.jsonl"))
    parser.add_argument("--configs", type=Path, default=Path("benchmarks/configs.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--ks", type=int, nargs="+", default=[1, 3, 5, 10])
    parser.add_argument("--ragas", action="store_true", help="add Ragas non-LLM context metrics")
    args = parser.parse_args(argv)

    settings = load_settings()
    configure_logging(settings.log_level, settings.log_json)
    configs = [RunConfig(**c) for c in json.loads(args.configs.read_text(encoding="utf-8"))]

    embedders: dict[str, BGEEmbeddings] = {}
    rerankers: dict[str, BGEReranker] = {}

    def factory(cfg: RunConfig) -> RetrievalService:
        if cfg.embedding_model not in embedders:
            embedders[cfg.embedding_model] = BGEEmbeddings(
                cfg.embedding_model, settings.embedding_query_instruction, settings.embedding_device,
                settings.embedding_batch_size,
            )
        emb = embedders[cfg.embedding_model]
        store = ChromaDocumentStore(settings.chroma_dir, cfg.collection_name, emb.model_name)
        reranker = None
        if cfg.use_reranker:
            if cfg.reranker_model not in rerankers:
                rerankers[cfg.reranker_model] = BGEReranker(
                    cfg.reranker_model, settings.embedding_device, settings.reranker_max_length,
                    settings.reranker_batch_size,
                )
            reranker = rerankers[cfg.reranker_model]
        return RetrievalService(store, emb, reranker, settings)

    report = run_benchmark(args.benchmark, configs, factory, ks=args.ks)

    if args.ragas:
        from app.evaluation.ragas_eval import build_ragas_rows, evaluate_non_llm

        items = load_benchmark(args.benchmark)
        for cfg, run in zip(configs, report["runs"], strict=True):
            rows = build_ragas_rows(factory(cfg), items, run["_contexts"])
            run["ragas"] = evaluate_non_llm(rows)

    path = save_report(report, args.output_dir)
    summary = [
        {"config": r["config"]["name"], "kb_size": r["knowledge_base_size"], **r["aggregate"],
         **{f"latency_{k}": v for k, v in r["latency"].items()}, **r.get("ragas", {})}
        for r in report["runs"]
    ]
    print(json.dumps(summary, indent=2))
    for r in report["runs"]:
        checks = r["checks"]
        if checks["missing_labelled_chunk_ids"] or checks["questions_found_verbatim_in_index"]:
            print(f"WARNING [{r['config']['name']}]: {checks}", file=sys.stderr)
    print(f"Saved: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
