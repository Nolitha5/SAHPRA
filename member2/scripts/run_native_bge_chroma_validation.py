"""ACTUAL ChromaDB+BGE technical index validation against all uploaded real PDFs.

No mocked Chroma, no hash-demo model, and no regulatory approval. Designed to run
on the team's workstation after the `vector` and `models` optional dependencies
and Hugging Face model weights have been installed. Exits with 2 if blocked.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
import sys
import traceback
import hashlib
from datetime import datetime, timezone
from pathlib import Path


def preflight() -> dict:
    status={name:importlib.util.find_spec(name) is not None for name in
            ['chromadb','sentence_transformers','transformers','torch','fitz','pydantic']}
    return {'packages':status,'chroma_ready':status['chromadb'],
            'embedding_ready':status['sentence_transformers'],
            'status':'READY_TO_ATTEMPT' if all(status.values()) else 'BLOCKED_MISSING_DEPENDENCIES',
            'note':'Package presence does not prove BGE weights are cached or native operations work.'}


def token_length_audit(embedder, chunks) -> dict:
    """Check actual Hugging Face token counts; whitespace chunk sizes can exceed model context."""
    model = embedder._model
    tokenizer = getattr(model, 'tokenizer', None)
    max_seq = getattr(model, 'max_seq_length', None)
    if tokenizer is None or not isinstance(max_seq, int) or max_seq < 1:
        return {'status':'NOT_VERIFIED', 'reason':'Tokenizer or max_seq_length unavailable'}
    lengths = []
    for i in range(0, len(chunks), 32):
        batch = tokenizer([c.text for c in chunks[i:i+32]],
                          add_special_tokens=True, truncation=False,
                          return_attention_mask=False)
        lengths.extend(len(x) for x in batch['input_ids'])
    oversized = [c.chunk_id for c, length in zip(chunks,lengths) if length>max_seq]
    return {'status':'AUDITED', 'max_seq_length':max_seq,
            'max_observed_tokens':max(lengths,default=0),
            'chunks_over_model_limit':len(oversized),
            'example_oversized_chunk_ids':oversized[:12],
            'warning':'Model can silently truncate text; use model-token chunking before scientific comparison' if oversized else None}


def run_native(root:Path,index:Path,db_dir:Path,models:list[str],offline:bool=False,top_k:int=5,
               window_tokens:int=384,overlap_tokens:int=64,reserved_tokens:int=8,
               use_parent_chunks:bool=False) -> dict:
    from m2.technical_benchmark import source_pdf_map,verify_chunks,verify_probes,evaluate_navigation
    from m2.schemas import RegulatoryChunk
    from m2.embeddings import SentenceTransformerEmbedder
    from m2.storage import ChromaVectorStore
    from m2.token_safe_index import TokenIndexConfig, split_regulatory_chunks
    manifest=json.loads((index/'REAL_CORPUS_MANIFEST.json').read_text())
    chunks=[RegulatoryChunk.model_validate_json(line) for line in (index/'REGULATORY_CHUNKS.jsonl').read_text().splitlines() if line.strip()]
    verify_chunks(chunks,manifest)
    source_pdf_map(root,manifest)  # full byte-hash verification before any embedding
    suite=json.loads((root/'examples/researcher_navigation_probes_v0.6.json').read_text())
    probes=verify_probes(root,manifest,suite['probes'])
    digest=hashlib.sha256(''.join(sorted(s['sha256'] for s in manifest['sources'])).encode()).hexdigest()[:12]
    entries=[]
    for model in models:
        embedder=SentenceTransformerEmbedder(model,local_files_only=offline)
        token_audit=token_length_audit(embedder,chunks)
        if use_parent_chunks:
            index_chunks = chunks
            split_report = {'status':'LEGACY_WHITESPACE_CHUNKS', 'warning':'May be silently truncated',
                            'indexed_chunks':len(chunks),'regulatory_approved':False}
        else:
            tokenizer = getattr(embedder._model, 'tokenizer', None)
            max_seq = getattr(embedder._model, 'max_seq_length', None)
            if tokenizer is None or not isinstance(max_seq,int):
                raise RuntimeError('Fast model tokenizer and max sequence length required')
            cfg = TokenIndexConfig(model_id=model,max_model_tokens=max_seq,
                                   window_tokens=window_tokens,overlap_tokens=overlap_tokens,
                                   reserved_tokens=reserved_tokens)
            index_chunks, split_report = split_regulatory_chunks(chunks, tokenizer, cfg)
            safe_audit = token_length_audit(embedder,index_chunks)
            if safe_audit.get('status')!='AUDITED' or safe_audit['chunks_over_model_limit']:
                raise RuntimeError('Token-aware chunk audit failed; refuse Chroma upsert')
            split_report['final_token_audit']=safe_audit
        cfg_digest=hashlib.sha256(f'{model}|{window_tokens}|{overlap_tokens}|{reserved_tokens}|{use_parent_chunks}'.encode()).hexdigest()[:8]
        prefix=f'm2tec-{digest}-{cfg_digest}'
        # Every model/chunk configuration receives an isolated Chroma collection.
        store=ChromaVectorStore(embedder,str(db_dir),collection_prefix=prefix)
        store.upsert(index_chunks)
        if store.count()!=len(index_chunks):
            raise RuntimeError(f'Index count mismatch for {model}: {store.count()} vs {len(index_chunks)}')
        reopened=ChromaVectorStore(embedder,str(db_dir),collection_prefix=prefix)
        if reopened.count()!=len(index_chunks):raise RuntimeError('Persistent reopening failed')
        if {c.chunk_id for c in reopened.all_chunks()} != {c.chunk_id for c in index_chunks}:
            raise RuntimeError('Persistent chunk identity mismatch')
        query_results=[reopened.search(p['question'],top_k) for p in probes]
        measured=evaluate_navigation(probes,query_results,k=top_k)
        entries.append({'model':model,'embedding_dimension':embedder.dimension,
                        'backend':'NATIVE_CHROMADB','collection':reopened.collection_name,
                        'persisted_count':reopened.count(),
                        'chunking_report':split_report,
                        'persistence_check':'PASS_REOPEN_AND_IDS',
                        'token_length_audit':token_audit,
                        'probe_navigation_metrics':measured})
    return {'status':'PASS_TECHNICAL_NATIVE_RUN','models':entries,
            'real_uploaded_documents':len(manifest['sources']),'chunks':len(chunks),
            'source_pdf_sha256_verified':True,'research_status':'NOT_EXPERT_LABELLED',
            'regulatory_source_approval':False,'regulatory_decision_ready':False,
            'note':'These are author-created navigation probes, not regulatory relevance grades.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--index',default='artifacts/real_corpus')
    p.add_argument('--chroma-dir',default='artifacts/v0.6/native_chroma')
    p.add_argument('--model',action='append',default=[],help='Repeat for multiple models')
    p.add_argument('--window-tokens',type=int,default=384)
    p.add_argument('--overlap-tokens',type=int,default=64)
    p.add_argument('--reserve-tokens',type=int,default=8)
    p.add_argument('--legacy-parent-chunks',action='store_true',help='Audited old word chunks; not token safe')
    p.add_argument('--offline',action='store_true',help='Require locally cached Hugging Face model')
    p.add_argument('--out',default='validation/v0.6_NATIVE_CHROMA_BGE_REPORT.json')
    a=p.parse_args()
    root=a.root.resolve()
    out=(root/a.out).resolve() if not Path(a.out).is_absolute() else Path(a.out)
    report={'timestamp_utc':datetime.now(timezone.utc).isoformat(),
            'environment_preflight':preflight(),
            'status':'BLOCKED','native_chromadb_executed':False,
            'bge_weights_loaded':False}
    if report['environment_preflight']['status']!='READY_TO_ATTEMPT':
        report['reason']='Missing dependencies; see environment_preflight.packages'
        exit_code=2
    else:
        try:
            models=a.model or ['BAAI/bge-large-en-v1.5']
            report.update(run_native(root,root/a.index,root/a.chroma_dir,models,offline=a.offline,window_tokens=a.window_tokens,
                                         overlap_tokens=a.overlap_tokens,reserved_tokens=a.reserve_tokens,
                                         use_parent_chunks=a.legacy_parent_chunks))
            report['native_chromadb_executed']=True
            report['bge_weights_loaded']=True
            exit_code=0
        except Exception as exc:
            report.update(status='FAIL_AFTER_PREFLIGHT',reason=f'{type(exc).__name__}: {exc}',
                          traceback_tail=''.join(traceback.format_exception(exc))[-2500:])
            exit_code=1
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(out),'reason':report.get('reason'),
                      'native_chromadb_executed':report['native_chromadb_executed']},indent=2))
    return exit_code
if __name__=='__main__':raise SystemExit(main())
