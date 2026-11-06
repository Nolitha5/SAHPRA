"""Build an isolated ChromaDB/BGE index from locally reviewed WHO monograph PDFs.

NEVER fetches online documents, never approves regulatory applicability or makes decisions.
Requires human attestations already present and SHA-256 verification.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from m2.schemas import RegulatoryChunk
from m2.registry import SourceRegistry, file_sha256
from m2.storage import ChromaVectorStore
from m2.embeddings import build_embedder


def build(root:Path,*,model:str,index_dir:Path, offline:bool=False)->dict:
    reg_path=root/'phint_approved_sources.json'
    registry=SourceRegistry.load(reg_path)
    if not registry.records:
        raise RuntimeError('No locally reviewed monographs; use phint_manage.py import-reviewed first')
    chunks=[]
    for source in registry.records.values():
        review_file=root/(source.source_id+'.review.json')
        if not review_file.is_file():
            raise RuntimeError('Missing reviewer attestation for '+source.source_id)
        review=json.loads(review_file.read_text(encoding='utf-8'))
        pdf=Path(review['retained_pdf'])
        if not pdf.is_file() or file_sha256(pdf)!=source.sha256:
            raise RuntimeError('PDF provenance/hash mismatch: '+source.source_id)
        if not source.approved or not source.provenance_verified:
            raise RuntimeError('Unapproved source: '+source.source_id)
        file=root/(source.source_id+'.jsonl')
        for line in file.read_text(encoding='utf-8').splitlines():
            c=RegulatoryChunk.model_validate_json(line)
            if c.source_id!=source.source_id:
                raise RuntimeError('Chunk source mix-up detected')
            chunks.append(c)
    if not chunks:
        raise RuntimeError('No reviewed chunks to index')
    embed=build_embedder(model,offline=offline)
    store=ChromaVectorStore(embed,str(index_dir),collection_prefix='phint')
    store.upsert(chunks)
    if store.count()<len(chunks):
        raise RuntimeError('Incomplete Chroma indexing')
    stats={'status':'INDEXED_LOCALLY_REVIEWED_PHINT_REFERENCES', 'backend':'ChromaDB',
        'model':model, 'count':store.count(), 'unique_sources':len(registry.records),
        'collection':store.collection_name, 'publisher_bytes_verified':False,
        'reviewer_credentials_independently_verified':False,
        'regulatory_authorisation':False}
    index_dir.mkdir(parents=True,exist_ok=True)
    (index_dir/'PHINT_CHROMA_MANIFEST.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
    return stats

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--reviewed-root',type=Path,default=ROOT/'pharmacopoeia/reviewed_local')
    ap.add_argument('--index',type=Path,default=ROOT/'local_indexes/phint_chroma')
    ap.add_argument('--model',default='BAAI/bge-large-en-v1.5')
    ap.add_argument('--offline',action='store_true')
    a=ap.parse_args()
    print(json.dumps(build(a.reviewed_root,model=a.model,index_dir=a.index,offline=a.offline),indent=2))

if __name__=='__main__': main()
