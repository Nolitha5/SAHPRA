"""Verify raw monograph PDF identity/hash and create a status report (not regulatory approval)."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from m2.pharmacopoeia import PharmacopoeiaCatalogue
from m2.phint_acquisition import verify_pdf_bytes

def run(folder=ROOT/'pharmacopoeia/acquired_pending_review'):
 cat=PharmacopoeiaCatalogue.load(ROOT/'pharmacopoeia/WHO_PHINT_RESEARCH_CATALOGUE_v0.7.json')
 rows=[]
 for entry in cat.entries:
  if entry.kind!='API_MONOGRAPH':continue
  f=Path(folder)/(entry.id+'.pdf')
  if not f.exists():
   rows.append({'id':entry.id,'status':'MISSING'});continue
  try:
   checked=verify_pdf_bytes(entry,f.read_bytes())
   rows.append({'id':entry.id,'status':'IDENTITY_VERIFIED_PENDING_EDITION_RIGHTS_AND_APPLICABILITY',**checked})
  except Exception as e:rows.append({'id':entry.id,'status':'INVALID_OR_WRONG_MONOGRAPH','error':str(e)})
 return {'rows':rows,'verified':sum(r['status'].startswith('IDENTITY_VERIFIED_') for r in rows),
         'approved':0,'chroma_bge_executed':False}
if __name__=='__main__':
 r=run();print(json.dumps(r,indent=2));sys.exit(0 if r['verified']==4 else 2)
