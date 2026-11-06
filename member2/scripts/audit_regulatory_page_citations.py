"""Independently verify every stored regulatory passage exists on its cited original PDF page."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from m2.citation_audit import audit_pdf_passages

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,default=Path('.'))
    p.add_argument('--output',type=Path,default=Path('validation/v1.1_PAGE_ANCHOR_AUDIT.json'))
    args=p.parse_args()
    result=audit_pdf_passages(args.root)
    path=args.output if args.output.is_absolute() else args.root/args.output
    path.parent.mkdir(exist_ok=True,parents=True)
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'pdfs':result['pdfs_sha256_verified'],
                      'passages':result['passages_audited'],
                      'errors':result['unanchored_passages'],'report':str(path)},indent=2))
    return 0 if result['status']=='PASS_ANCHORED_TECHNICAL_AUDIT' else 1
if __name__=='__main__':raise SystemExit(main())
