"""Multi-configuration experimental runner. Must have approved real PDFs and expert labels."""
import argparse,json
from m2.experiments import run_grid
p=argparse.ArgumentParser()
p.add_argument('--registry',default='local_indexes/sources.json')
p.add_argument('--pdf-dir',default='regulatory_sources')
p.add_argument('--gold',required=True)
p.add_argument('--out',default='artifacts/real-grid')
p.add_argument('--models',nargs='+',default=['BAAI/bge-large-en-v1.5','BAAI/bge-m3','sentence-transformers/all-MiniLM-L6-v2'])
p.add_argument('--sizes',type=int,nargs='+',default=[256,512,1024])
p.add_argument('--overlaps',type=int,nargs='+',default=[64,128])
p.add_argument('--top-k',type=int,default=5)
p.add_argument('--tokenizer',required=True)
p.add_argument('--rerank',action='store_true')
p.add_argument('--offline',action='store_true')
p.add_argument('--mlflow',action='store_true')
a=p.parse_args()
r=run_grid(a.registry,a.pdf_dir,a.gold,a.out,a.models,a.sizes,a.overlaps,k=a.top_k,
    tokenizer_name=a.tokenizer,use_reranker=a.rerank,offline_models=a.offline,enable_mlflow=a.mlflow)
print(json.dumps(r,indent=2))
