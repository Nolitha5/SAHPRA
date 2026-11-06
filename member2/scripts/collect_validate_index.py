"""Acquire official regulatory PDFs, verify identity/provenance, rebuild TECHNICAL preview.

Execution modes: --status (always safe); --download (internet required);
--index (requires the three bundled PDFs and includes every validated local candidate).
No command conveys domain approval or certifies an assessor finding.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import re
import csv

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / 'regulatory_sources/OFFICIAL_ADDITIONAL_DOWNLOAD_QUEUE.json'
DIR = ROOT / 'regulatory_sources/additional_unapproved'
OUTPUT = ROOT / 'artifacts/real_corpus'
BASE = {'ICH-M4Q-R1':ROOT/'regulatory_sources/user_supplied_unapproved/ICH-M4Q-R1.pdf',
        'ICH-Q11':ROOT/'regulatory_sources/user_supplied_unapproved/ICH-Q11.pdf',
        'WHO-TRS1010-A10':ROOT/'regulatory_sources/user_supplied_unapproved/WHO-TRS1010-Annex10.pdf'}

def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def inspect_source(s:dict, path:Path)->dict:
    out={'source_id':s['source_id'],'filename':s['filename'],'path':str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
         'status':'MISSING','regulatory_approved':False,'legal_reuse_reviewed':False}
    if not path.is_file():return out
    out['bytes']=path.stat().st_size
    out['sha256']=sha256(path)
    if path.stat().st_size < 1000:
        out.update(status='REJECT_NON_PDF_OR_TRUNCATED',reason='File too small');return out
    if path.open('rb').read(5)!=b'%PDF-':
        out.update(status='REJECT_NON_PDF_OR_TRUNCATED',reason='No PDF signature');return out
    try:
        import fitz
        with fitz.open(path) as doc:
            pages=doc.page_count
            if pages<1:raise ValueError('No pages')
            txt=' '.join(doc[i].get_text() for i in range(min(5,pages)))
            out['pages']=pages
            out['extractable_characters_first_five_pages']=len(txt)
            if len(txt.strip()) < 120:
                out.update(status='NEEDS_OCR_REVIEW',reason='Scanned/unextractable page text');return out
            marker=re.sub('[^A-Z0-9]+','',s['document_code'].upper())
            normalized=re.sub('[^A-Z0-9]+','',txt.upper())
            aliases={'SAHPGLPEM02':'QUALITYANDBIOEQUIVALENCE', 'Q11QAS':'Q11'}
            expected=aliases.get(marker,marker)
            if expected not in normalized:
                out.update(status='NEEDS_IDENTITY_REVIEW',reason=f'Code/title not recognized in first 5 pages: {s["document_code"]}');return out
            if s['source_id']=='SAHPRA-PEM-02-V9':
                out['sahpra_version_review_required']=True
                out['sahpra_document_expected_listed_version']='v9 (2025-10-23)'
            out['status']='EXTRACTABLE_PDF_TECHNICAL_ONLY'
    except Exception as e:
        out.update(status='REJECT_UNREADABLE_PDF',reason=str(e))
    return out

def run(*, download:bool=False,index:bool=False,include_conditional:bool=False,
        selected_ids:list[str]|None=None,report_path:Path|None=None)->dict:
    entries=json.loads(QUEUE.read_text(encoding='utf-8'))['sources']
    if selected_ids:
        valid={x['source_id'] for x in entries}
        unknown=set(selected_ids)-valid
        if unknown:raise ValueError('Unknown source ids: '+', '.join(sorted(unknown)))
    selected=[x for x in entries if (not selected_ids or x['source_id'] in selected_ids)
              and (include_conditional or x.get('selection_group')!='conditional_biologics')]
    DIR.mkdir(parents=True,exist_ok=True)
    acquisition=[]
    if download:
        from acquire_official_additional import fetch_source
        for s in selected:
            p=DIR/s['filename']
            if p.exists():
                acquisition.append({'source_id':s['source_id'],'status':'PRESENT_NOT_OVERWRITTEN'});continue
            try:
                metadata=fetch_source(s,DIR)
                acquisition.append({'source_id':s['source_id'],'status':'DOWNLOADED_PENDING_REVIEW','sha256':metadata['sha256']})
            except Exception as exc:
                acquisition.append({'source_id':s['source_id'],'status':'DOWNLOAD_FAILED','error':str(exc)})
    inspections=[inspect_source(s, DIR/s['filename']) for s in entries]
    indexed=None
    if index:
        from m2.real_corpus import register_additional_from_queue, index_uploaded
        sources=dict(BASE)
        register_additional_from_queue(QUEUE)
        for s, result in zip(entries,inspections):
            if result['status']=='EXTRACTABLE_PDF_TECHNICAL_ONLY':
                if s.get('selection_group')=='conditional_biologics' and not include_conditional:continue
                sources[s['source_id']]=DIR/s['filename']
        OUTPUT.mkdir(parents=True,exist_ok=True)
        manifest=index_uploaded(sources,OUTPUT)
        indexed={'source_count':manifest['unique_document_count'],'chunk_count':manifest['indexed_chunk_count'],
                 'backend':manifest['index_backend'],'embedding':manifest['embedding_model'],
                 'regulatory_approved':False}
    coverage_csv=ROOT/'artifacts/real_corpus/LIVE_CORPUS_COVERAGE.csv'
    coverage_csv.parent.mkdir(parents=True,exist_ok=True)
    with coverage_csv.open('w',newline='',encoding='utf-8-sig') as output_csv:
        writer=csv.DictWriter(output_csv,fieldnames=['source_id','document_code','priority','status','pages','sha256','filename','regulatory_approved'])
        writer.writeheader()
        byid={item['source_id']:item for item in entries}
        for item in inspections:
            writer.writerow({k:item.get(k,byid.get(item['source_id'],{}).get(k,'')) for k in writer.fieldnames})
    report={'generated_at_utc':datetime.now(timezone.utc).isoformat(),
            'bundle_sources':3,'additional_candidates':len(entries),'additional_present':sum(x['status']=='EXTRACTABLE_PDF_TECHNICAL_ONLY' for x in inspections),
            'download_performed':download,'acquisition_events':acquisition,'document_inspections':inspections,
            'index_rebuilt':indexed,'all_sources_domain_approved':False,
            'limitations':['Download requires open access from official domains on an internet-connected workstation.',
            'Technical PDF signature/title checks are NOT expert review or legal reuse permission.',
            'Downloaded files are not SAHPRA-approved as sources for an individual dossier.',
            'SQLite/hash search is a technical preview, not ChromaDB/BGE model retrieval.']}
    target=report_path or ROOT/'artifacts/real_corpus/ACQUISITION_AND_COVERAGE_REPORT_v0.4.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--download',action='store_true',help='Download publisher-hosted PDF candidates on an internet-connected machine')
    p.add_argument('--index',action='store_true',help='Rebuild offline technical index from available PDFs (not BGE/ChromaDB)')
    p.add_argument('--include-conditional',action='store_true',help='Include biologics-only Q6B after scoping decision')
    p.add_argument('--id',action='append',default=[],help='Download only specified source ID; repeat as needed')
    p.add_argument('--report-output',type=Path)
    a=p.parse_args()
    sys.path.insert(0,str(ROOT/'src'))
    r=run(download=a.download,index=a.index,include_conditional=a.include_conditional,
          selected_ids=a.id,report_path=a.report_output)
    print(json.dumps({'additional_candidates':r['additional_candidates'],'additional_present':r['additional_present'],
                      'indexed':r['index_rebuilt'],'download_failures':sum(e['status']=='DOWNLOAD_FAILED' for e in r['acquisition_events']),
                      'regulatory_approval':False},indent=2))
    if any(e['status']=='DOWNLOAD_FAILED' for e in r['acquisition_events']):raise SystemExit(2)

if __name__=='__main__':main()
