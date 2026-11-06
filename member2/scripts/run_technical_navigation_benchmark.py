"""Run an honest full-corpus lexical/TF-IDF technical benchmark (NOT Chroma/BGE)."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from datetime import datetime, timezone
from m2.technical_benchmark import benchmark_from_files


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--output',type=Path,default=Path('artifacts/v0.6/navigation_benchmark.json'))
    p.add_argument('--top-k',type=int,default=5)
    a=p.parse_args()
    result=benchmark_from_files(a.root,top_k=a.top_k)
    result['run_timestamp_utc']=datetime.now(timezone.utc).isoformat()
    out=a.output if a.output.is_absolute() else a.root/a.output
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'saved_to':str(out),'queries':result['query_count'],
                      'results':{k:v['aggregate'] for k,v in result['models'].items()},
                      'warning':result['evaluation_type']},indent=2))

if __name__=='__main__':main()
