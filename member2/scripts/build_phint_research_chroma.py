"""Technical-only Chroma+BGE preview from identity-checked pending PDFs. NOT regulatory-approved evidence."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from m2.pharmacopoeia import PharmacopoeiaCatalogue
from m2.phint_acquisition import verify_pdf_bytes
from m2.chunking import chunks_from_pdf
from m2.embeddings import build_embedder
from m2.storage import ChromaVectorStore


def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--pdf-dir',type=Path,default=ROOT/'pharmacopoeia/acquired_pending_review')
 ap.add_argument('--index',type=Path,default=ROOT/'local_indexes/phint_research_UNAPPROVED')
 ap.add_argument('--model',default='BAAI/bge-large-en-v1.5')
 ap.add_argument('--offline',action='store_true')
 args=ap.parse_args()
 cat=PharmacopoeiaCatalogue.load(ROOT/'pharmacopoeia/WHO_PHINT_RESEARCH_CATALOGUE_v0.7.json')
 manifest=[];chunks=[]
 for entry in cat.entries:
  if entry.kind != 'API_MONOGRAPH':continue
  f=args.pdf_dir/(entry.id+'.pdf')
  if not f.is_file(): continue
  checked=verify_pdf_bytes(entry,f.read_bytes())
  c=chunks_from_pdf(str(f),entry.id,size=180,overlap=30,default_section=f'WHO_PhInt/{entry.id}')
  if not c:raise RuntimeError('No text extracted from '+str(f))
  for ch in c:
   ch.metadata.update({'compendium':'Ph.Int.','regulatory_authorised':False,'source_sha256':checked['sha256'],'substance':entry.substance})
  chunks.extend(c)
  manifest.append({'id':entry.id, 'sha256':checked['sha256'], 'pages':checked['pages'],'chunks':len(c),'rights_and_applicability_reviewed':False})
 if not chunks: raise RuntimeError('No identity-verified local WHO PDFs; run scripts/acquire_who_monographs.py or manually save PDFs into the incoming folder')
 emb=build_embedder(args.model,offline=args.offline)
 store=ChromaVectorStore(emb,str(args.index),collection_prefix='phint-research-NOTAPPROVED')
 store.upsert(chunks)
 fresh=ChromaVectorStore(emb,str(args.index),collection_prefix='phint-research-NOTAPPROVED')
 if fresh.count()<len(chunks):raise RuntimeError('Chroma reopen/persistence test failed')
 sample=fresh.search('pharmacopoeia identity assay requirements',3)
 report={'status':'TECHNICAL_INDEX_ONLY_NOT_REGULATORY_APPROVED','model':args.model,
         'persistent_count':fresh.count(),'chunks_input':len(chunks),'sources':manifest,
         'reopened':True,'retrieval_smoke_count':len(sample),'regulatory_approval_or_rejection':None,
         'must_not_be_connected_to_M1_M5':True}
 args.index.mkdir(parents=True,exist_ok=True)
 (args.index/'RESEARCH_INDEX_REPORT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
