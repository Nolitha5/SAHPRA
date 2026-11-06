"""Reproducible retrieval scoring. M4 owns system-wide A-D experimental harness."""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from .schemas import GoldQuery, BenchmarkReport, EvidenceRequest
from .retrieval import EvidenceService

def retrieval_metrics(retrieved: list[str], relevant: list[str], k: int) -> dict[str,float]:
    if k < 1: raise ValueError("k >=1 required")
    selected = retrieved[:k]
    gold = set(relevant)
    hits = [1 if a in gold else 0 for a in selected]
    precis = sum(hits)/k
    recall = sum(hits)/len(gold) if gold else 0.0
    mrr = next((1.0/(i+1) for i,h in enumerate(hits) if h),0.0)
    dcg = sum(h/math.log2(i+2) for i,h in enumerate(hits))
    ideal = sum(1.0/math.log2(i+2) for i in range(min(k,len(gold))))
    return {"precision_at_k":precis,"recall_at_k":recall,"mrr_at_k":mrr,
            "ndcg_at_k":dcg/ideal if ideal else 0.0}

def benchmark(service: EvidenceService, gold: list[GoldQuery], *, k: int=5,
              require_expert_labels: bool=False) -> BenchmarkReport:
    if not gold: raise ValueError("Gold query set must not be empty")
    per = []
    for q in gold:
        result = service.retrieve(EvidenceRequest(request_id=q.query_id,question=q.question,
                       requesting_agent="EVALUATION",top_k=k,filters=q.filters))
        ids = [x.chunk_id for x in result.evidence]
        metric = retrieval_metrics(ids,q.relevant_chunk_ids,k)
        per.append({"query_id":q.query_id,"status":result.status.value,"retrieved_chunk_ids":ids,
                    "relevant_chunk_ids":q.relevant_chunk_ids,**metric})
    fields = ["precision_at_k","recall_at_k","mrr_at_k","ndcg_at_k"]
    agg = {field:sum(row[field] for row in per)/len(per) for field in fields}
    return BenchmarkReport(config={"k":k,"retrieval":service._metadata(),"label_verification":
                 "NOT_CONFIRMED_EXPERT" if not require_expert_labels else "USER_ASSERTED_EXPERT"},
            evaluated_queries=len(gold),aggregate=agg,per_query=per)

def save_report(report: BenchmarkReport, output: str):
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    data=report.model_dump(mode="json");data["created_at_utc"]=datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(data,indent=2),encoding="utf-8")


def evaluate_grid(corpus_chunks, registry, gold, *, backend_factory, embedder_factory,
                  chunk_sizes=(256,512,1024), model_names=("BAAI/bge-large-en-v1.5", "BAAI/bge-m3", "sentence-transformers/all-MiniLM-L6-v2"),
                  overlaps=(64,128),k=5, output_dir="artifacts/grid"):
    """Optional model comparison on *actual* source chunks; creates one store per run.

    Re-chunking must occur upstream from raw page-level source text to make chunk-size trials
    valid. This function intentionally requires a caller-supplied backend_factory and a
    pre-chunked mapping by (size, overlap), rather than pretending to resplit existing chunks.
    """
    from .retrieval import RetrievalConfig, EvidenceService
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    summaries=[]
    for size in chunk_sizes:
        for overlap in overlaps:
            if overlap >= size: continue
            chunks=corpus_chunks.get((size,overlap))
            if chunks is None:
                raise ValueError(f"Missing source-rechunked records for {(size,overlap)}")
            for model in model_names:
                embedder=embedder_factory(model)
                store=backend_factory(embedder,f"{model.replace('/','_')}-{size}-{overlap}")
                store.upsert(chunks)
                service=EvidenceService(store,registry,config=RetrievalConfig(index_id=model,
                                   min_query_token_overlap=0.0))
                report=benchmark(service,gold,k=k)
                slug=f"{model.replace('/','_')}-{size}-{overlap}.json"
                save_report(report,str(out/slug))
                summaries.append({"embedding_model":model,"size":size,"overlap":overlap,**report.aggregate})
    (out/"summary.json").write_text(json.dumps(summaries,indent=2),encoding="utf-8")
    return summaries
