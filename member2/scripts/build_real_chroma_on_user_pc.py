"""Re-embed the verified three-upload corpus into real ChromaDB using BGE.

INTENDED TO RUN ON THE USER'S NETWORK/MODEL-CAPABLE MACHINE, NOT a fake Chroma adapter.
Local source byte hashes and chunk IDs are checked against the preview manifest. Does
not mark regulatory applicability approved or serve results without additional gating.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
from m2.embeddings import SentenceTransformerEmbedder
from m2.storage import ChromaVectorStore
from m2.schemas import RegulatoryChunk

def main():
    p=argparse.ArgumentParser();p.add_argument('--index',type=Path,default=Path('artifacts/real_corpus'))
    p.add_argument('--chroma-dir',type=Path,default=Path('artifacts/real_chroma'))
    p.add_argument('--model',default='BAAI/bge-large-en-v1.5');p.add_argument('--offline-models',action='store_true')
    a=p.parse_args()
    meta=json.loads((a.index/'REAL_CORPUS_MANIFEST.json').read_text(encoding='utf-8'))
    from m2.real_corpus import hash_file
    candidate_dirs=[Path('regulatory_sources/user_supplied_unapproved'),Path('regulatory_sources/additional_unapproved')]
    for s in meta['sources']:
        candidates=[folder/s['pdf_file'] for folder in candidate_dirs]
        matches=[file for file in candidates if file.is_file() and hash_file(file)==s['sha256']]
        if len(matches)!=1:raise RuntimeError('Missing, ambiguous or hash-mismatched source: '+s['pdf_file'])
    chunks=[RegulatoryChunk.model_validate_json(s) for s in (a.index/'REGULATORY_CHUNKS.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    embedder=SentenceTransformerEmbedder(a.model,local_files_only=a.offline_models)
    store=ChromaVectorStore(embedder,str(a.chroma_dir),collection_prefix='regulatory_technical_unapproved')
    store.upsert(chunks)
    if store.count()!=len(chunks):raise RuntimeError(f'Missing indexed chunks ({store.count()} / {len(chunks)})')
    test=store.search('analytical procedures validation',limit=2)
    if not test:raise RuntimeError('Actual Chroma query returned no results')
    report={'backend':'ACTUAL_CHROMADB','model':embedder.name,'vector_dimension':embedder.dimension,
            'collection':store.collection_name,'chunk_count':store.count(),'source_count':len(meta['sources']),
            'verified_source_hashes':True,'query_smoke_chunks':[c.chunk_id for c,_ in test],
            'regulatory_source_approval':False,'experiment_label':'TECHNICAL_ONLY_NO_GROUND_TRUTH'}
    out=a.chroma_dir/'ACTUAL_CHROMA_RUN.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
