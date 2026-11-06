"""Human-attested source curation, separate from data acquisition and indexing.

This utility checks file integrity but cannot verify a signer's credentials, regulator
adoption status or licensing; the project governance team must do those checks.
"""
from __future__ import annotations
from datetime import date,datetime,timezone
from pathlib import Path
import json
from .schemas import SourceRecord
from .source_acquisition import OFFICIAL_SOURCES
from .registry import file_sha256,SourceRegistry


def curate(acquisition_json:str|Path, pdf_dir:str|Path, registry_path:str|Path,
           *, reviewer_id:str, approved_version:str, licence_attestation:str,
           reviewed_regulatory_applicability:str, effective_from:str|None=None,
           cover_discrepancy_resolution:str|None=None) -> dict:
    if min(len(reviewer_id.strip()),len(approved_version.strip()))<2:raise ValueError('Reviewer and verified version required')
    if len(licence_attestation.strip())<20:raise ValueError('Provide documented licensing/access assessment')
    if len(reviewed_regulatory_applicability.strip())<20:raise ValueError('Provide documented applicability assessment')
    obj=json.loads(Path(acquisition_json).read_text(encoding='utf-8'))
    source=next((s for s in OFFICIAL_SOURCES if s.source_id==obj.get('source_id')),None)
    if not source:raise ValueError('Unknown source identifier')
    pdf=Path(pdf_dir)/f'{source.source_id}.pdf'
    if not pdf.is_file() or obj.get('sha256')!=file_sha256(pdf):
        raise ValueError('Source PDF not found or checksum does not match acquisition record')
    if obj.get('suspected_cover_version_inconsistency') and not (cover_discrepancy_resolution and len(cover_discrepancy_resolution.strip())>=20):
        raise ValueError('Resolve the suspected document cover-version inconsistency before source approval')
    from urllib.parse import urlparse
    if urlparse(obj.get('download_url','')).hostname not in {
            'www.sahpra.org.za','sahpra.org.za','database.ich.org','cdn.who.int','www.who.int'}:
        raise ValueError('Source must be acquired from the authorised official host')
    rec=SourceRecord(source_id=source.source_id,authority=source.authority,title=source.document_title,
         document_code=source.document_code,version=approved_version,
         effective_from=date.fromisoformat(effective_from) if effective_from else None,
         url=source.entry_url,license_note=licence_attestation,
         approved=True,provenance_verified=True,sha256=obj['sha256'],
         notes='REVIEWER ATTESTATION (unverified credentials): '+reviewed_regulatory_applicability)
    reg=SourceRegistry.load(registry_path)
    reg.register(rec)
    reg.save(registry_path)
    attestation={'source_id':source.source_id,'reviewer_id':reviewer_id,
        'reviewed_at_utc':datetime.now(timezone.utc).isoformat(),
        'verified_version_claim':approved_version,'source_sha256':obj['sha256'],
        'licence_attestation':licence_attestation,
        'regulatory_applicability_assessment':reviewed_regulatory_applicability,
        'cover_discrepancy_resolution':cover_discrepancy_resolution,
        'caution':'Signer credentials, licence claims and adoption conditions are not independently checked by this script.'}
    (Path(pdf_dir)/f'{source.source_id}.review.json').write_text(json.dumps(attestation,indent=2),encoding='utf-8')
    return {'registered':source.source_id,'approved_from_explicit_reviewer_attestation':True,
            'credentials_independently_verified':False,'registry':str(registry_path)}
