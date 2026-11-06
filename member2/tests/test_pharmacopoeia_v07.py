from __future__ import annotations
import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import fitz
import pytest
from m2.pharmacopoeia import (PharmacopeialEntry, PharmacopoeiaCatalogue, collect_status,
    import_verified_monograph, acquire_pdf)
from m2.pharmacopoeia_service import lookup_compendial_evidence
from m2.embeddings import HashEmbedder
from m2.storage import MemoryVectorStore
from m2.registry import SourceRegistry
from m2.retrieval import EvidenceService, RetrievalConfig
from m2.schemas import RegulatoryChunk, EvidenceRequest, EvidenceFilters

ROOT=Path(__file__).resolve().parents[1]
CAT=ROOT/'pharmacopoeia/WHO_PHINT_RESEARCH_CATALOGUE_v0.7.json'

@pytest.fixture
def catalogue():return PharmacopoeiaCatalogue.load(CAT)

def test_metadata_no_monograph_text_included(catalogue):
    assert len(catalogue.entries)==7
    assert all(not e.content_included for e in catalogue.entries)
    assert all(e.publisher=='WHO' for e in catalogue.entries)

def test_find_paracetamol_by_name_alias_and_cas(catalogue):
    for key,cas in [('Paracetamol',None),('Acetaminophen',None),('', '103-90-2')]:
        m=catalogue.resolve(key,cas=cas)
        assert m.status=='REFERENCE_ONLY_REVIEW_REQUIRED'
        assert m.candidates[0]['id']=='WHO-PHINT-PARACETAMOL-API'
        assert m.candidates[0]['metadata_only']

def test_no_sponsor_dosage_form_auto_match(catalogue):
    assert catalogue.resolve('Paracetamol tablets').status=='NOT_FOUND'
    assert catalogue.resolve('Paracetamol',ctd_section='3.2.P.5').status=='NOT_FOUND'

def test_cas_name_conflict_prevents_reliable_match(catalogue):
    assert catalogue.resolve('Paracetamol',cas='111-11-1').status=='IDENTIFIER_CONFLICT'

def test_general_notice_not_specific_monograph(catalogue):
    assert catalogue.resolve('General Notices — Definition').status=='NOT_FOUND'

def test_status_explicit_zero_present(catalogue,tmp_path):
    out=collect_status(catalogue,tmp_path)
    assert out['present_pdf_count']==0 and out['indexed_pdf_count']==0
    assert all(x['status']=='REFERENCE_ONLY_NOT_ACQUIRED' for x in out['entries'])

def test_public_pdf_candidate_is_not_verified_or_downloaded_implicitly(catalogue,tmp_path):
    entry=catalogue.by_id['WHO-PHINT-PARACETAMOL-API']
    assert entry.pdf_url and entry.pdf_download_status.startswith('OFFICIAL_DOMAIN_CANDIDATE')
    assert not (tmp_path / f'{entry.id}.pdf').exists()

def test_invalid_host_rejected():
    entry=json.loads(CAT.read_text())['entries'][0]
    entry['online_url']='http://localhost:8000/private'
    with pytest.raises(ValueError):PharmacopeialEntry.model_validate(entry)

def test_non_pdf_responses_blocked(catalogue,tmp_path):
    e=catalogue.by_id['WHO-PHINT-AMOXICILLIN-TRIHYDRATE-API']
    fake=SimpleNamespace(url=e.pdf_url,content=b'<html>no access</html>',raise_for_status=lambda:None)
    with pytest.raises(ValueError,match='intact PDF'):
        acquire_pdf(e,tmp_path,session=SimpleNamespace(get=lambda *args,**kwargs:fake))
    assert not list(tmp_path.glob('*.pdf'))

def test_reference_only_never_returns_evidence(catalogue):
    ev=EvidenceService(MemoryVectorStore(HashEmbedder()),SourceRegistry())
    x=lookup_compendial_evidence(catalogue,ev,substance='Paracetamol',
        question='Paracetamol assay requirements',requesting_agent='S4_CONTROL')
    assert x['lookup_status']=='MONOGRAPH_REFERENCE_ONLY_NOT_INDEXED_OR_APPROVED'
    assert x['evidence']==[] and x['regulatory_approval_or_rejection'] is None

def test_unverified_effective_date_gated(catalogue):
    e=catalogue.by_id['WHO-PHINT-PARACETAMOL-API']
    from m2.schemas import SourceRecord
    reg=SourceRegistry([SourceRecord(source_id=e.id,authority='WHO Ph.Int.',title=e.title,
         document_code='Ph.Int.:WHO-PHINT-PARACETAMOL-API',version='reviewer-approved-2025',
         approved=True,provenance_verified=True,sha256='a'*64)])
    ev=EvidenceService(MemoryVectorStore(HashEmbedder()),reg)
    x=lookup_compendial_evidence(catalogue,ev,substance='Paracetamol',as_of=date(2024,1,1),
          question='identity assay monograph',requesting_agent='S4_CONTROL')
    assert x['lookup_status']=='EFFECTIVE_DATE_NOT_VERIFIED'

def _create_synthetic_pdf(path:Path, name:str):
    pdf=fitz.open();page=pdf.new_page();page.insert_text((50,65), name + ' synthetic example only')
    page.insert_text((50,90), 'This text is not a regulatory requirement. It is a test fixture.')
    pdf.save(str(path));pdf.close()

def test_import_requires_all_attestations(catalogue,tmp_path):
    e=catalogue.by_id['WHO-PHINT-PARACETAMOL-API']
    p=tmp_path/'f.pdf';_create_synthetic_pdf(p,'Paracetamol')
    with pytest.raises(ValueError,match='attestations required'):
        import_verified_monograph(entry=e,pdf_path=p,output=tmp_path/'reviewed',
            approved_edition='13th Edition',reviewer_id='x',rights_attestation='yes',
            applicability_attestation='yes',edition_verification_note='yes')

def test_import_requires_edition_discrepancy_resolution(catalogue,tmp_path):
    e=catalogue.by_id['WHO-PHINT-AMOXICILLIN-TRIHYDRATE-API']
    p=tmp_path/'f.pdf';_create_synthetic_pdf(p,'Amoxicillin trihydrate')
    with pytest.raises(ValueError,match='Resolve'):
        import_verified_monograph(entry=e,pdf_path=p,output=tmp_path/'reviewed',
            approved_edition='Research edition checked',reviewer_id='Research Test User',
            rights_attestation='Synthetic PDF test fixture reused by its creator',
            applicability_attestation='Synthetic test scenario with no regulatory authority',
            edition_verification_note='Edition not resolved; pending reviewer')

def test_import_detects_wrong_pdf(catalogue,tmp_path):
    e=catalogue.by_id['WHO-PHINT-PARACETAMOL-API']
    p=tmp_path/'f.pdf';_create_synthetic_pdf(p,'Ibuprofen')
    with pytest.raises(ValueError,match='expected monograph identity'):
        import_verified_monograph(entry=e,pdf_path=p,output=tmp_path/'reviewed',
            approved_edition='Research test edition example',reviewer_id='Research Test User',
            rights_attestation='Synthetic PDF test fixture reused by its creator',
            applicability_attestation='Synthetic test scenario with no regulatory authority',
            edition_verification_note='Edition discrepancy resolved in synthetic test')

def test_import_scoped_reviewed_pdf_and_retrieve(catalogue,tmp_path):
    e=catalogue.by_id['WHO-PHINT-PARACETAMOL-API']
    pdf=tmp_path/'f.pdf';_create_synthetic_pdf(pdf,'Paracetamol assay identity')
    output=tmp_path/'reviewed'
    r=import_verified_monograph(entry=e,pdf_path=pdf,output=output,
        approved_edition='Research synthetic test edition',reviewer_id='Research Test User',
        rights_attestation='Synthetic PDF test fixture reused by its creator',
        applicability_attestation='Synthetic test scenario with no regulatory authority',
        edition_verification_note='Edition discrepancy resolved in synthetic test')
    assert r['chunk_count'] > 0 and Path(r['retained_pdf']).is_file()
    reg=SourceRegistry.load(output/'phint_approved_sources.json')
    chunks=[RegulatoryChunk.model_validate_json(s) for s in (output/(e.id+'.jsonl')).read_text().splitlines()]
    assert all(c.source_id == e.id and c.page == 1 for c in chunks)
    store=MemoryVectorStore(HashEmbedder());store.upsert(chunks)
    service=EvidenceService(store,reg,config=RetrievalConfig(min_query_token_overlap=0.01))
    x=lookup_compendial_evidence(catalogue,service,substance='Paracetamol',
          question='Paracetamol assay identity synthetic',requesting_agent='S4_CONTROL')
    assert x['lookup_status']=='RETRIEVAL_FOUND'
    assert x['evidence'][0]['source_id']==e.id
    assert x['regulatory_approval_or_rejection'] is None

def test_api_m1_m5_reference_only(monkeypatch,demo):
    from fastapi.testclient import TestClient
    import m2.api as api
    monkeypatch.setenv('M2_PHINT_CATALOGUE',str(CAT))
    api.set_runtime(demo)
    try:
        resp=TestClient(api.app).post('/m2/phint/evidence',json={
            'substance':'Paracetamol','question':'What is its assay requirement?',
            'requesting_agent':'S5_REFERENCE_STANDARDS'})
        assert resp.status_code==200
        body=resp.json()
        assert body['lookup_status']=='MONOGRAPH_REFERENCE_ONLY_NOT_INDEXED_OR_APPROVED'
        assert body['human_review_required'] and not body['evidence']
        assert body['regulatory_approval_or_rejection'] is None
    finally:api.set_runtime(None)
