"""Register a manually downloaded WHO monograph PDF in pending quarantine, after identity checks."""
from __future__ import annotations
import argparse,hashlib,json,shutil,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from m2.pharmacopoeia import PharmacopoeiaCatalogue
from m2.phint_acquisition import verify_pdf_bytes

def register(file: Path, ident: str, folder: Path):
    cat=PharmacopoeiaCatalogue.load(ROOT/'pharmacopoeia/WHO_PHINT_RESEARCH_CATALOGUE_v0.7.json')
    entry=cat.by_id[ident]
    assert entry.kind == 'API_MONOGRAPH'
    file=Path(file)
    check=verify_pdf_bytes(entry,file.read_bytes())
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    destination=folder/f'{ident}.pdf'
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest()!=check['sha256']:
            raise FileExistsError('Existing different PDF: preserve original and resolve source/version manually')
    else:shutil.copyfile(file,destination)
    rec={'status':'MANUALLY_SUPPLIED_PENDING_REVIEW','source':str(file),'id':ident,
         'received_at':datetime.now(timezone.utc).isoformat(),'retained':str(destination), **check}
    (folder/(ident+'.acquisition.json')).write_text(json.dumps(rec,indent=2),encoding='utf-8')
    return rec

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--id',required=True)
    p.add_argument('--file',required=True,type=Path)
    p.add_argument('--out',type=Path,default=ROOT/'pharmacopoeia/acquired_pending_review')
    a=p.parse_args()
    print(json.dumps(register(a.file,a.id,a.out),indent=2))
