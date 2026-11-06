"""Official-source inventory and gated acquisition. Never auto-approves a guideline.

Links are official publishers found during research on 15 October 2026.
Downloaded bytes must be verified by a qualified domain reviewer before indexing.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import hashlib
import json

OFFICIAL_HOSTS = frozenset({
    'www.sahpra.org.za', 'sahpra.org.za', 'database.ich.org',
    'www.ich.org', 'ich.org', 'www.who.int', 'who.int', 'cdn.who.int',
})

@dataclass(frozen=True)
class OfficialSource:
    source_id: str
    authority: str
    document_code: str
    document_title: str
    entry_url: str
    pdf_url: str | None
    version_hint: str
    notes: str

OFFICIAL_SOURCES: tuple[OfficialSource, ...] = (
    OfficialSource('SAHPRA-PEM-02-V9','SAHPRA','SAHPGL-PEM-02',
        'Quality and Bioequivalence Guideline',
        'https://www.sahpra.org.za/document/quality-and-bioequivalence/',
        'https://www.sahpra.org.za/wp-content/uploads/2022/01/SAHPGL-PEM-02_v9_Quality-and-Bioequivalence-Guideline.pdf',
        '9 (23 October 2025)',
        'OFFICIAL PDF QUALITY FLAG: its first displayed page says v8 and subsequent pages say v9; reviewer must inspect history and confirm actual version before approval.'),
    OfficialSource('ICH-M4Q-R1','ICH','M4Q(R1)',
        'Common Technical Document — Quality',
        'https://www.ich.org/page/ctd',
        'https://database.ich.org/sites/default/files/M4Q_R1_Guideline.pdf',
        'R1 (2002)', 'Confirm this is the applicable CTD quality structure and not a superseding revision.'),
    OfficialSource('ICH-Q11','ICH','Q11',
        'Development and Manufacture of Drug Substances',
        'https://www.ich.org/page/quality-guidelines',
        'https://database.ich.org/sites/default/files/Q11_Guideline.pdf',
        'Q11 (2012)', 'Confirm latest revision and local adoption before scientific use.'),
    OfficialSource('WHO-TRS1010-A10','WHO','TRS 1010 Annex 10',
        'WHO Guidelines on Stability Testing of Active Pharmaceutical Ingredients and Finished Pharmaceutical Products',
        'https://www.who.int/publications/m/item/trs1010-annex10',
        'https://cdn.who.int/media/docs/default-source/medicines/norms-and-standards/guidelines/regulatory-standards/trs1010-annex10-who-stability-testing-of-active-pharmaceutical-ingredients.pdf?download=true&sfvrsn=7cb7a4c9_4',
        '2018', 'Confirm 2018 edition and jurisdiction/applicability.'),
    OfficialSource('ICH-Q6A','ICH','Q6A',
        'Specifications: Test Procedures and Acceptance Criteria',
        'https://www.ich.org/page/quality-guidelines', None,
        '1999', 'Official quality-guideline listing verified; official PDF download URL still requires verification.'),
    OfficialSource('ICH-Q2-R2','ICH','Q2(R2)',
        'Validation of Analytical Procedures',
        'https://www.ich.org/page/quality-guidelines', None,
        '2023', 'Official quality-guideline listing verified; applicable regional implementation requires checking.'),
    OfficialSource('ICH-Q14','ICH','Q14',
        'Analytical Procedure Development',
        'https://www.ich.org/page/quality-guidelines', None,
        '2023', 'Official quality-guideline listing verified; applicability review required.'),
    OfficialSource('ICH-Q3A-R2','ICH','Q3A(R2)',
        'Impurities in New Drug Substances',
        'https://www.ich.org/page/quality-guidelines', None,
        '2006', 'Official quality-guideline listing verified; official PDF URL still requires verification.'),
)


def catalogue() -> list[dict]:
    return [asdict(s) | {'download_status':'NOT_ACQUIRED', 'source_approved':False,
                         'expert_labels_verified':False} for s in OFFICIAL_SOURCES]


def save_catalogue(path: str | Path) -> Path:
    dest = Path(path); dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({'catalogue_checked_utc':'2026-10-15',
        'status':'DISCOVERY_ONLY_NOT_A_VERIFIED_INDEX', 'sources':catalogue()},indent=2),encoding='utf-8')
    return dest


def acquire_official_pdf(source_id:str, target_dir:str|Path, *, session=None, max_bytes=25_000_000):
    """Acquire only direct official PDF. Produce hold-for-review metadata, not approval.

    All redirects must stay on approved official hosts. No sponsored-case files, no auto index.
    """
    source=next((s for s in OFFICIAL_SOURCES if s.source_id==source_id),None)
    if source is None: raise ValueError(f'Unknown source ID: {source_id}')
    if source.pdf_url is None: raise ValueError('Official direct PDF URL not independently verified; supply manually after review')
    import requests
    sess=session or requests.Session()
    response=sess.get(source.pdf_url,stream=True,timeout=40,allow_redirects=True)
    response.raise_for_status()
    for hop in list(getattr(response,'history',[]))+[response]:
        parsed=urlparse(hop.url)
        if parsed.scheme != 'https' or (parsed.hostname or '').lower() not in OFFICIAL_HOSTS:
            response.close()
            raise ValueError('Download redirected outside approved official HTTPS hosts')
    buffer=bytearray()
    try:
        for chunk in response.iter_content(chunk_size=65536):
            if not chunk:continue
            buffer.extend(chunk)
            if len(buffer)>max_bytes: raise ValueError('PDF exceeds acquisition size limit')
    finally:
        response.close()
    if not bytes(buffer[:5]) == b'%PDF-': raise ValueError('Publisher response is not a PDF')
    import fitz
    document=fitz.open(stream=bytes(buffer),filetype='pdf')
    if not document.page_count:raise ValueError('No PDF pages')
    first_pages=' '.join(p.get_text() for p in list(document)[:4])[:20000]
    page_count=document.page_count;document.close()
    target_dir=Path(target_dir);target_dir.mkdir(parents=True,exist_ok=True)
    pdf_path=target_dir/f'{source_id}.pdf'
    if pdf_path.exists():raise FileExistsError('Source PDF exists: manually version or archive before replacement')
    pdf_path.write_bytes(buffer)
    info={'source_id':source_id,'authority':source.authority,'document_code':source.document_code,
          'version_hint_UNVERIFIED':source.version_hint,'publisher_url':source.entry_url,
          'download_url':response.url,'sha256':hashlib.sha256(buffer).hexdigest(),
          'bytes':len(buffer),'pdf_pages':page_count,'acquired_at_utc':datetime.now(timezone.utc).isoformat(),
          'source_approved':False,'provenance_verified':False,'reviewer_required':True,
          'suspected_cover_version_inconsistency':source_id=='SAHPRA-PEM-02-V9' and ('v8' in first_pages.lower() and 'v9' in first_pages.lower()),
          'notes':source.notes}
    (target_dir/f'{source_id}.acquisition.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    return info


def main():
    import argparse
    parser=argparse.ArgumentParser(description='Official regulatory source acquisition; never auto-approves')
    g=parser.add_mutually_exclusive_group(required=True)
    g.add_argument('--catalogue',action='store_true')
    g.add_argument('--download',choices=[s.source_id for s in OFFICIAL_SOURCES])
    parser.add_argument('--out',default='regulatory_sources')
    args=parser.parse_args()
    if args.catalogue:
        p=save_catalogue(Path(args.out)/'OFFICIAL_SOURCE_CATALOGUE.json')
        print(json.dumps({'catalogue':str(p),'approved':False}))
    else:
        print(json.dumps(acquire_official_pdf(args.download,args.out),indent=2))
if __name__=='__main__':main()
