"""CLI for demo, indexing, search, S.4 review and benchmark."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .runtime import AppConfig, M2Runtime
from .schemas import SourceRecord, RegulatoryChunk, EvidenceRequest, S4ReviewRequest, GoldQuery
from .chunking import chunks_from_pdf
from .registry import SourceRegistry, file_sha256
from .evaluation import benchmark, save_report

def load_demo(runtime, examples="examples"):
    base = Path(examples)
    for src in json.loads((base/"synthetic_registry.json").read_text(encoding="utf-8")):
        runtime.registry.register(SourceRecord.model_validate(src))
    runtime.index([RegulatoryChunk.model_validate(x) for x in json.loads((base/"synthetic_chunks.json").read_text(encoding="utf-8"))])

def load_json(path): return json.loads(Path(path).read_text(encoding="utf-8"))

def main(argv=None):
    parser = argparse.ArgumentParser(description="SAHPRA Member 2 RKB, RERA and S.4")
    parser.add_argument("--config",default="config/default.json")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("demo")
    sub.add_parser("stats")
    p=sub.add_parser("ingest-pdf");p.add_argument("--source",required=True);p.add_argument("--pdf",required=True);p.add_argument("--size",type=int,default=512);p.add_argument("--overlap",type=int,default=128)
    p=sub.add_parser("index-chunks");p.add_argument("--input",required=True)
    p=sub.add_parser("register-source");p.add_argument("--input",required=True)
    p=sub.add_parser("search");p.add_argument("question");p.add_argument("--top-k",type=int,default=5);p.add_argument("--from-demo",action="store_true")
    p=sub.add_parser("review-s4");p.add_argument("--input",required=True);p.add_argument("--from-demo",action="store_true")
    p=sub.add_parser("benchmark");p.add_argument("--gold",required=True);p.add_argument("--k",type=int,default=3);p.add_argument("--out",default="artifacts/retrieval_benchmark.json");p.add_argument("--from-demo",action="store_true")
    args=parser.parse_args(argv)
    cfg=AppConfig.from_file(args.config)
    if args.command=="register-source":
        # Administrative manifest updates should not require a GPU, ChromaDB or downloaded models.
        registry=SourceRegistry.load(cfg.registry_path)
        doc=SourceRecord.model_validate(load_json(args.input))
        registry.register(doc)
        registry.save(cfg.registry_path)
        print(json.dumps({"registered":doc.source_id,"registry":cfg.registry_path}));return
    runtime=M2Runtime(cfg)
    if args.command=="ingest-pdf":
        src=runtime.registry.get(args.source)
        if src.sha256 and file_sha256(args.pdf)!=src.sha256:
            raise ValueError("PDF hash does not match verified source manifest")
        chunks=chunks_from_pdf(args.pdf,args.source,size=args.size,overlap=args.overlap)
        runtime.index(chunks)
        print(json.dumps({"indexed":len(chunks),"source":args.source,"storage":runtime.stats()},indent=2));return
    if args.command=="index-chunks":
        chunks=[RegulatoryChunk.model_validate(x) for x in load_json(args.input)];runtime.index(chunks)
        print(json.dumps({"indexed":len(chunks),"storage":runtime.stats()},indent=2));return
    if args.command=="demo" or getattr(args,"from_demo",False): load_demo(runtime)
    if args.command=="stats":print(json.dumps(runtime.stats(),indent=2));return
    if args.command=="demo":
        req=EvidenceRequest(request_id="demo-1",requesting_agent="S1_IDENTITY",
            question="analytical validation accuracy precision",top_k=3)
        evidence=runtime.evidence.retrieve(req)
        s4=runtime.s4.review(S4ReviewRequest.model_validate(load_json("examples/synthetic_s4_case.json")))
        print(json.dumps({"warning":"SYNTHETIC DEMO - NO REAL REGULATORY GUIDELINES, NOT VALIDATED",
                          "evidence_result":evidence.model_dump(mode="json"),
                          "s4_statuses":{f.ctd_section:f.status.value for f in s4.findings},
                          "stats":runtime.stats()},indent=2));return
    if args.command=="search":
        req=EvidenceRequest(request_id="cli",requesting_agent="CLI",question=args.question,top_k=args.top_k)
        print(runtime.evidence.retrieve(req).model_dump_json(indent=2));return
    if args.command=="review-s4":
        req=S4ReviewRequest.model_validate(load_json(args.input))
        print(runtime.s4.review(req).model_dump_json(indent=2));return
    if args.command=="benchmark":
        gold=[GoldQuery.model_validate(x) for x in load_json(args.gold)]
        report=benchmark(runtime.evidence,gold,k=args.k)
        save_report(report,args.out)
        print(report.model_dump_json(indent=2));return

if __name__=="__main__":main()
