"""Genuine Chroma persistent-store smoke test; records BLOCKED if not installed.

No mock is accepted by this runner. Embeddings are deterministic synthetic vectors so
Chroma persistence is tested independently of model downloads; the BGE test is separate.
"""
from __future__ import annotations
import importlib.util, json, tempfile, traceback
from pathlib import Path
from datetime import datetime, timezone


def validate_chroma(path: str | None = None) -> dict:
    result={'test':'NATIVE_CHROMADB_PERSISTENCE', 'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'status':'BLOCKED','reason':None, 'tests':[], 'uses_real_regulatory_material':False,
            'uses_real_embedding_model':False}
    if importlib.util.find_spec('chromadb') is None:
        result['reason']='chromadb package is not installed in this Python environment'
        return result
    from .embeddings import HashEmbedder
    from .storage import ChromaVectorStore
    from .schemas import RegulatoryChunk
    try:
        with tempfile.TemporaryDirectory() if path is None else _kept_dir(path) as dest:
            embedder=HashEmbedder()
            store=ChromaVectorStore(embedder,str(dest),collection_prefix='smoketest')
            docs=[RegulatoryChunk(chunk_id='test-c1',source_id='SYNTHETIC',section='3.2.S.4.1',
                text='synthetic assay specifications test acceptance criteria'),
                RegulatoryChunk(chunk_id='test-c2',source_id='SYNTHETIC',section='3.2.S.7',
                text='synthetic storage stability time points')]
            store.upsert(docs)
            assert store.count()==2
            result['tests'].append('upsert_and_count')
            assert store.search('assay specifications',2)
            result['tests'].append('query_returns_passages')
            store2=ChromaVectorStore(embedder,str(dest),collection_prefix='smoketest')
            assert store2.count()==2
            assert {x.chunk_id for x in store2.all_chunks()}=={'test-c1','test-c2'}
            result['tests'].append('reopen_persists_chunks')
            store2.upsert([docs[0]])
            assert store2.count()==2
            result['tests'].append('idempotent_upsert')
            result['status']='PASS';result['reason']=None
            result['chroma_version']=__import__('chromadb').__version__
    except Exception as exc:
        result['status']='FAIL';result['reason']=f'{type(exc).__name__}: {exc}'
        result['traceback_tail']=''.join(traceback.format_exception(exc))[-1600:]
    return result

class _kept_dir:
    def __init__(self,path): self.path=Path(path)
    def __enter__(self):self.path.mkdir(parents=True,exist_ok=True);return str(self.path)
    def __exit__(self,*args):return False


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--dir',default=None)
    parser.add_argument('--out',default='validation/CHROMA_RUNTIME_CHECK.json')
    a=parser.parse_args()
    report=validate_chroma(a.dir)
    p=Path(a.out);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='PASS' else 2 if report['status']=='BLOCKED' else 1
if __name__=='__main__':raise SystemExit(main())
