"""Run ONLY on internet-connected researcher workstation. Acquires official PDFs.

Documents stay unapproved and must be reviewed before use in regulated assessments.
No data uploads; no third-party mirror; strict allowed-HTTPS redirects, no overwrite.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

HOSTS={'database.ich.org','www.ema.europa.eu','www.sahpra.org.za'}

def fetch_source(src:dict,target:Path,max_bytes=35_000_000):
    import requests
    import fitz
    url=src['url'];u=urlparse(url)
    if u.scheme!='https' or u.hostname not in HOSTS:raise ValueError(f'Unapproved host: {url}')
    target.mkdir(parents=True,exist_ok=True)
    dest=target/src['filename']
    if dest.exists():raise FileExistsError(f'Cannot overwrite: {dest}')
    with requests.Session() as session:
        with session.get(url,stream=True,timeout=65,allow_redirects=True) as r:
            r.raise_for_status()
            for hop in list(r.history)+[r]:
                parsed=urlparse(hop.url)
                if parsed.scheme!='https' or parsed.hostname not in HOSTS:raise ValueError('Redirect left official allowlist')
            contents=bytearray()
            for block in r.iter_content(chunk_size=65536):
                contents.extend(block)
                if len(contents)>max_bytes:raise ValueError('PDF size limit exceeded')
            final=r.url
    if contents[:5]!=b'%PDF-':raise ValueError('Not PDF')
    with fitz.open(stream=bytes(contents),filetype='pdf') as pdf:
        if pdf.page_count<=0:raise ValueError('Empty PDF')
        pages=pdf.page_count
        first=' '.join(pdf[i].get_text() for i in range(min(4,pages)))[:20000]
    dest.write_bytes(contents)
    meta={"source_id":src['source_id'],"file":src['filename'],"sha256":hashlib.sha256(contents).hexdigest(),
          "pages":pages,"download_url":final,"reference_url":src['reference_url'],"version_hint":src['version_hint'],
          "source_approved":False,"regulatory_applicability_verified":False,
          "requires_domain_reviewer":True,"notes":src['notes'],"first_page_maybe_v8":'SAHPRA' in src['source_id'] and 'v8' in first.lower()}
    (target/(src['filename']+'.acquisition.json')).write_text(json.dumps(meta,indent=2),encoding='utf-8')
    return meta

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalogue',default='regulatory_sources/OFFICIAL_ADDITIONAL_DOWNLOAD_QUEUE.json')
    p.add_argument('--dest',default='regulatory_sources/additional_unapproved')
    p.add_argument('--id',action='append',default=[])
    args=p.parse_args()
    sources=json.loads(Path(args.catalogue).read_text(encoding='utf-8'))['sources']
    selected=[s for s in sources if not args.id or s['source_id'] in args.id]
    if args.id and len(selected)!=len(set(args.id)):raise ValueError('Unknown source ID')
    results=[]
    for s in selected:
        try:results.append({'source_id':s['source_id'],'outcome':'ACQUIRED_PENDING_REVIEW','details':fetch_source(s,Path(args.dest))})
        except Exception as exc:results.append({'source_id':s['source_id'],'outcome':'FAILED','error':str(exc)})
    print(json.dumps(results,indent=2))
    if any(r['outcome']=='FAILED' for r in results):raise SystemExit(1)
if __name__=='__main__':main()
