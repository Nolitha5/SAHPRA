"""Index the user-supplied, non-binding IPRP quality-assessor guide with PDF-page anchors."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import fitz


def build(source:Path,dest:Path):
    blob=source.read_bytes()
    if not blob.startswith(b'%PDF-'):raise ValueError('Expected the original assessor guidance PDF')
    out=[]
    with fitz.open(stream=blob,filetype='pdf') as pdf:
        first=pdf[0].get_text()
        if not ('GUIDANCE' in first.upper() and 'DRUG SUBSTANCE' in first.upper() and 'IPRP' in first.upper()):
            raise ValueError('IPRP source identity check failed')
        for i,page in enumerate(pdf,1):
            text=page.get_text(sort=True).strip()
            if not text:continue
            ctd='3.2.S.4' if 14<=i<=17 else '3.2.S.5' if i==18 else '3.2.S'
            out.append({'source_id':'IPRP-QWGG-2018-v1.1', 'document_code':'IPRP QWGG Quality Assessors Drug Substance',
                        'title':'Guidance for Quality Assessors – Drug Substance',
                        'document_version':'1.1 (2018-09-20)', 'authority':'IPRP',
                        'source_role':'NONBINDING_ASSESSOR_MODEL_GUIDANCE',
                        'applicability':'CHEMICAL_DRUG_SUBSTANCES_ONLY',
                        'regulatory_approved':False, 'human_review_required':True,
                        'original_pdf_page':i,'ctd_section_hint':ctd,
                        'text':text,'sha256':hashlib.sha256(blob).hexdigest()})
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('w',encoding='utf-8') as f:
        for row in out:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    report={'indexed_pages':len(out),'original_pdf_sha256':hashlib.sha256(blob).hexdigest(),
            'status':'INDEXED_NONBINDING_GUIDANCE_PENDING_DOMAIN_REVIEW',
            'source_notes':'IPRP model guide is expressly nonmandatory; not a SAHPRA approval rule',
            's4_pdf_pages':[14,15,16,17],'s5_pdf_page':18,
            'created_utc':datetime.now(timezone.utc).isoformat()}
    dest.with_suffix('.report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pdf',type=Path,required=True);p.add_argument('--out',type=Path,default=Path('artifacts/iprp/IPRP_PAGE_INDEX.jsonl'))
    a=p.parse_args();print(json.dumps(build(a.pdf,a.out),indent=2))
