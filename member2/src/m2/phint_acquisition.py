"""WHO Ph.Int. public PDF acquisition with link fallbacks and conservative identity verification.

Downloads are staging only, never approved regulatory evidence. All HTTP paths are
untrusted until downloaded PDF pages are matched to the expected substance/CAS.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import Any

from bs4 import BeautifulSoup
import fitz
import requests
from .pharmacopoeia import PharmacopeialEntry, PharmacopoeiaCatalogue, norm

TRUSTED = {"digicollections.net", "www.digicollections.net"}


def trusted(url: str) -> bool:
    p = urlparse(url)
    return p.scheme == 'https' and p.hostname in TRUSTED and not p.username and not p.password


def publisher_candidates(entry: PharmacopeialEntry, html: str | None = None) -> list[str]:
    """Explicit URL first, then WHO's 'Open section in PDF format' target."""
    urls = ([entry.pdf_url] if entry.pdf_url else [])
    if html:
        soup = BeautifulSoup(html, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = urljoin(entry.online_url, link['href'])
            label = link.get_text(' ',strip=True).lower()
            if ('open section in pdf' in label or '.pdf' in href.lower()) and trusted(href):
                urls.append(href)
    return list(dict.fromkeys(u for u in urls if u and trusted(u)))


def verify_pdf_bytes(entry: PharmacopeialEntry, payload: bytes) -> dict[str,Any]:
    if len(payload) < 1024 or not payload.startswith(b'%PDF-'):
        raise ValueError('Not a valid-looking WHO PDF')
    with fitz.open(stream=payload,filetype='pdf') as doc:
        if doc.page_count < 1 or doc.page_count > 300:
            raise ValueError('Unexpected monograph page count')
        pages = [doc[i].get_text(sort=True) for i in range(min(doc.page_count,2))]
        content = '\n'.join(pages)
        key = norm(entry.substance or '')
        if not key or key not in norm(content):
            raise ValueError('PDF substance identity differs from expected monograph')
        if entry.cas and entry.cas not in content:
            raise ValueError('PDF CAS identifier differs or is not present on leading pages')
        expected = [str(x) for x in (entry.substance, entry.cas)]
        edition_hits = re.findall(r'(?:International Pharmacopoeia\s*[-—]\s*)?(?:Twelfth|Thirteenth|Eleventh|Tenth)\s+Edition[^\n]{0,35}',content,re.I)
        return {'pages':doc.page_count, 'sha256':hashlib.sha256(payload).hexdigest(),
                'identity_checked':expected, 'edition_mentions':edition_hits[:6],
                'text_chars_first_pages':len(content),
                'edition_and_regulatory_applicability_approved':False}


def acquire(entry: PharmacopeialEntry, folder: Path, *, session=None) -> dict[str,Any]:
    if entry.kind != 'API_MONOGRAPH':
        raise ValueError('Only API monographs supported in this collection workflow')
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    target=folder/(entry.id+'.pdf')
    if target.exists():
        try:
            checked=verify_pdf_bytes(entry,target.read_bytes())
            return {'id':entry.id,'status':'PRESENT_PENDING_REVIEW','path':str(target),**checked}
        except Exception as e:
            return {'id':entry.id,'status':'EXISTING_PDF_UNVERIFIED', 'error':str(e), 'path':str(target)}
    sender = session or requests.Session()
    issues=[]
    candidate_urls = publisher_candidates(entry)
    try:
        response=sender.get(entry.online_url,timeout=25,allow_redirects=True)
        if trusted(response.url) and response.ok:
            candidate_urls = list(dict.fromkeys(candidate_urls+publisher_candidates(entry,response.text)))
        else: issues.append('WHO landing page unavailable')
    except requests.RequestException as e:
        issues.append('WHO landing page: '+type(e).__name__)
    for u in candidate_urls:
        try:
            res=sender.get(u,timeout=60,allow_redirects=True)
            if not trusted(res.url) or any(not trusted(h.url) for h in getattr(res,'history',[])):
                issues.append('UNTRUSTED_REDIRECT '+u); continue
            res.raise_for_status()
            checked=verify_pdf_bytes(entry,res.content)
            # Source bytes only; never mark legal authority/approval automatically.
            target.write_bytes(res.content)
            receipt={'id':entry.id,'status':'DOWNLOADED_PENDING_REVIEW','path':str(target),
                     'retrieved_from':res.url,'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
                     **checked}
            (folder/(entry.id+'.acquisition.json')).write_text(json.dumps(receipt,indent=2),encoding='utf-8')
            return receipt
        except (requests.RequestException,ValueError,RuntimeError) as e:
            issues.append(f'{u}: {type(e).__name__}: {str(e)[:150]}')
    return {'id':entry.id,'status':'DOWNLOAD_FAILED_OR_SOURCE_UNVERIFIED','online_url':entry.online_url,
            'candidate_pdf_urls':candidate_urls,'issues':issues,'manual_action':'Open WHO publisher page, choose Open section in PDF format, save the PDF and provide the file locally; do not use other-substance PDFs.'}


def acquire_four(catalogue: PharmacopoeiaCatalogue, folder: Path, *, session=None) -> dict[str,Any]:
    results=[acquire(e,folder,session=session) for e in catalogue.entries if e.kind=='API_MONOGRAPH']
    return {'status':'PENDING_REVIEW_NOT_AUTHORITATIVE','requested':len(results),
            'present':sum(r['status'] in {'DOWNLOADED_PENDING_REVIEW','PRESENT_PENDING_REVIEW'} for r in results),
            'entries':results}
