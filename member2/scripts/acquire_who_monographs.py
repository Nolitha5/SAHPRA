"""Acquire four WHO API monograph PDFs to unapproved quarantine. No auto-approval."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from m2.pharmacopoeia import PharmacopoeiaCatalogue
from m2.phint_acquisition import acquire_four

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--out',type=Path,default=ROOT/'pharmacopoeia/acquired_pending_review')
 p.add_argument('--report',type=Path,default=ROOT/'artifacts/phint_v0.8/WHO_ACQUISITION_REPORT.json')
 args=p.parse_args()
 catalogue=PharmacopoeiaCatalogue.load(ROOT/'pharmacopoeia/WHO_PHINT_RESEARCH_CATALOGUE_v0.7.json')
 result=acquire_four(catalogue,args.out)
 args.report.parent.mkdir(parents=True,exist_ok=True)
 args.report.write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
 print(json.dumps(result,indent=2,ensure_ascii=False))
 return 0 if result['present']==result['requested'] else 2
if __name__=='__main__':raise SystemExit(main())
