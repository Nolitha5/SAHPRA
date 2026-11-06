"""Actual source-anchored retrieval comparison independent of chunk identifiers."""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
from datetime import datetime,timezone
from itertools import product
from pydantic import BaseModel,Field
from .schemas import EvidenceFilters,EvidenceRequest
from .chunking import chunks_from_pdf
from .embeddings import build_embedder
from .registry import SourceRegistry,file_sha256
from .storage import ChromaVectorStore
from .retrieval import EvidenceService,RetrievalConfig,CrossEncoderReranker
from .evaluation import retrieval_metrics

class EvidenceAnchor(BaseModel):
    source_id: str
    section: str | None = None
    page: int | None = None

class AnchoredGoldQuery(BaseModel):
    query_id: str
    question: str
    relevant: list[EvidenceAnchor]=Field(min_length=1)
    filters: EvidenceFilters=Field(default_factory=EvidenceFilters)


def anchor_match(source_id: str,section: str,page: int|None,anchor: EvidenceAnchor):
    return source_id==anchor.source_id and (anchor.section is None or section==anchor.section) and (anchor.page is None or page==anchor.page)


def anchored_benchmark(service:EvidenceService, queries:list[AnchoredGoldQuery], k:int=5) -> dict:
    if not queries:raise ValueError("Missing expert labels")
    per=[]
    for q in queries:
        res=service.retrieve(EvidenceRequest(request_id=q.query_id,question=q.question,top_k=k,
                                             requesting_agent="BENCHMARK",filters=q.filters))
        retrieved=res.evidence
        ranks=[p for p in retrieved if any(anchor_match(p.source_id,p.section,p.page,a) for a in q.relevant)]
        # Source/page anchors can have several relevant chunks. A hit means any correct anchor retrieved.
        hits=[];covered=set()
        for passage in retrieved[:k]:
            matched=next((i for i,a in enumerate(q.relevant) if anchor_match(passage.source_id,passage.section,passage.page,a)),None)
            unique=(matched is not None and matched not in covered)
            hits.append(1 if unique else 0)
            if unique: covered.add(matched)
        import math
        precision=sum(hits)/k
        recall=len(covered)/len(q.relevant)
        mrr=next((1/(idx+1) for idx,v in enumerate(hits) if v),0.0)
        dcg=sum(h/math.log2(i+2) for i,h in enumerate(hits))
        ideal=sum(1/math.log2(i+2) for i in range(min(len(q.relevant),k)))
        per.append({"query_id":q.query_id,"status":res.status.value,"precision_at_k":precision,
                    "recall_at_k":recall,"mrr_at_k":mrr,"ndcg_at_k":dcg/ideal if ideal else 0,
                    "retrieved": [{"source_id":p.source_id,"section":p.section,"page":p.page,"chunk_id":p.chunk_id} for p in retrieved]})
    metric_fields=["precision_at_k","recall_at_k","mrr_at_k","ndcg_at_k"]
    return {"queries":len(queries),"aggregate":{key:sum(row[key] for row in per)/len(per) for key in metric_fields},"per_query":per}


def run_grid(registry_file:str, pdf_dir:str, labels_file:str, output_dir:str,
             models:list[str],sizes:list[int],overlaps:list[int],k:int=5,
             use_reranker:bool=False,tokenizer_name:str|None=None,offline_models:bool=False,
             enable_mlflow:bool=False):
    registry=SourceRegistry.load(registry_file)
    q=[AnchoredGoldQuery.model_validate(x) for x in json.loads(Path(labels_file).read_text())]
    real=[s for s in registry.records.values() if s.source_type.value=="regulatory" and s.approved and s.provenance_verified]
    if not real:raise ValueError("No approved, verified regulatory corpus in registry")
    for src in real:
        f=Path(pdf_dir)/f"{src.source_id}.pdf"
        if not f.is_file():raise FileNotFoundError(f"Expected approved local PDF: {f}")
        if not src.sha256 or file_sha256(f)!=src.sha256:
            raise ValueError(f"Unverified or mismatched source PDF hash: {src.source_id}")
    if not tokenizer_name:
        raise ValueError("Use --tokenizer with a fixed actual HF tokenizer for comparable chunk sizes")
    try:
        from transformers import AutoTokenizer
    except ImportError as e:
        raise RuntimeError('pip install -e ".[models]" to use a real tokenizer') from e
    tokenizer=AutoTokenizer.from_pretrained(tokenizer_name,local_files_only=offline_models,trust_remote_code=False)
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    reranker=CrossEncoderReranker(local_files_only=offline_models) if use_reranker else None
    summaries=[]
    for size,overlap in product(sizes,overlaps):
        if overlap>=size:continue
        chunks=[]
        for source in real:
            chunks+=chunks_from_pdf(str(Path(pdf_dir)/f"{source.source_id}.pdf"),source.source_id,
                                    size=size,overlap=overlap,tokenizer=tokenizer)
        for model in models:
            embedding=build_embedder(model,offline=offline_models)
            slug=hashlib.sha256(f"{model}:{size}:{overlap}".encode()).hexdigest()[:16]
            store=ChromaVectorStore(embedding,str(out/"indexes"/slug))
            store.upsert(chunks)
            service=EvidenceService(store,registry,config=RetrievalConfig(allow_synthetic=False,index_id=store.collection_name,
                min_query_token_overlap=0.0,hybrid_weight=0.5,candidate_multiplier=6),reranker=reranker)
            result=anchored_benchmark(service,q,k=k)
            record={"model":model,"size_tokens":size,"overlap_tokens":overlap,"reranked":use_reranker,
                    "tokenizer":tokenizer_name,"chunks":len(chunks),"results":result}
            (out/f"{slug}.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
            summaries.append({k:v for k,v in record.items() if k!='results'} | result['aggregate'])
    (out/'summary.json').write_text(json.dumps({"created_at":datetime.now(timezone.utc).isoformat(),
        "gold_label_review":"MUST_VERIFY_WITH_M5","results":summaries},indent=2),encoding="utf-8")
    if enable_mlflow:
        try:import mlflow
        except ImportError as e:raise RuntimeError('Install experiment extra: pip install -e ".[experiment]"') from e
        for item in summaries:
            with mlflow.start_run(run_name=f"m2-{item['model']}-{item['size_tokens']}-{item['overlap_tokens']}"):
                mlflow.log_params({key:value for key,value in item.items() if key in {'model','size_tokens','overlap_tokens','reranked','tokenizer'}})
                mlflow.log_metrics({key:item[key] for key in ('precision_at_k','recall_at_k','mrr_at_k','ndcg_at_k')})
    return summaries
