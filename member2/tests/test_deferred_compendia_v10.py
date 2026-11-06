import json
from datetime import date
from pathlib import Path
import pytest
from pydantic import ValidationError

from m2.deferred_handoff import SponsorClaim, build_handoff, dataset_readiness, load_cases
from m2.monograph_onboarding import ReviewedSourceProposal, inspect_candidate, stage_submission
from m2.pharmacopoeia import PharmacopoeiaCatalogue
from m2.compendia_ingest import init_db, build_discovery
import zipfile
import fitz

ROOT = Path(__file__).resolve().parents[1]
CAT = ROOT / 'pharmacopoeia/WHO_PHINT_RESEARCH_CATALOGUE_v0.7.json'


def test_four_cases_are_explicitly_synthetic():
    cases=load_cases(ROOT/'examples/deferred_s4_s5_synthetic_cases.json')
    assert len(cases)==4
    assert len({x.case_id for x in cases})==4


def test_all_four_cannot_be_autonomously_approved():
    cases=load_cases(ROOT/'examples/deferred_s4_s5_synthetic_cases.json')
    catalogue=PharmacopoeiaCatalogue.load(CAT)
    records=[build_handoff(x,catalogue) for x in cases]
    check=dataset_readiness(records)
    assert check['technical_handoff_status']=='PASS'
    assert check['no_autonomous_verdict'] and check['human_review_required']==4
    assert check['expert_validated'] is False
    assert check['s4_s5_regulatory_accuracy'] is None
    assert all(not x['regulatory_evidence'] for x in records)
    assert all(len(x['s4_nonbinding_review_checklists'])==5 for x in records)
    assert all(x['s5_nonbinding_review_checklist']['ctd_section']=='3.2.S.5' for x in records)


def test_identifier_mismatch_is_blocked():
    c=SponsorClaim(case_id='test-mismatch',drug_substance='Ibuprofen',cas='103-90-2')
    result=build_handoff(c,PharmacopoeiaCatalogue.load(CAT))
    assert result['who_catalogue']['status']=='IDENTIFIER_CONFLICT'
    assert result['regulatory_evidence']==[]
    assert any('identity check' in b for b in result['cross_member_issues'])


def test_unknown_substance_is_not_fabricated():
    c=SponsorClaim(case_id='test-unknown',drug_substance='Fictional-substance-name')
    result=build_handoff(c,PharmacopoeiaCatalogue.load(CAT))
    assert result['who_catalogue']['status']=='NOT_FOUND'
    assert result['drug_authorisation_decision'] is None


def test_biological_guidance_scope_is_flagged():
    c=SponsorClaim(case_id='test-bio',drug_substance='Paracetamol',product_type='BIOLOGICAL')
    result=build_handoff(c,PharmacopoeiaCatalogue.load(CAT))
    assert any('chemical-substance specific' in x for x in result['cross_member_issues'])
    assert result['requires_human_review']


def test_unreviewed_research_candidates_never_citations(tmp_path):
    arc=tmp_path/'general-notices [webofpharma.com].zip'
    with zipfile.ZipFile(arc,'w') as z:
        z.writestr('Ibuprofen.html','<html><title>Ibuprofen</title><article>Ibuprofen substance monograph research discovery only</article></html>')
    from m2.compendia_ingest import ARCHIVE_SPECS
    # The source is marked GENERAL_NOTICES, so it cannot qualify as an API monograph.
    db=tmp_path/'index.sqlite3'
    build_discovery(tmp_path,db,selected=[arc.name])
    result=build_handoff(SponsorClaim(case_id='test-research',drug_substance='Ibuprofen'),
                         PharmacopoeiaCatalogue.load(CAT),research_index=db,include_unreviewed_candidates=True)
    assert result['research_only_leads']==[]
    assert not result['regulatory_evidence']


def test_optional_research_discovery_returns_metadata_not_text(tmp_path):
    arc=tmp_path/'New folder (8).zip'
    with zipfile.ZipFile(arc,'w') as z:
        z.writestr('Ibuprofen.html','<html><title>Ibuprofen</title><article>Ibuprofen API research monograph content only</article></html>')
    db=tmp_path/'index.sqlite3'
    build_discovery(tmp_path,db,selected=[arc.name])
    result=build_handoff(SponsorClaim(case_id='test-discover',drug_substance='Ibuprofen'),
                         PharmacopoeiaCatalogue.load(CAT),research_index=db,include_unreviewed_candidates=True)
    assert result['research_only_leads']
    assert all(x['regulatory_evidence'] is False for x in result['research_only_leads'])
    assert all('preview_text' not in x for x in result['research_only_leads'])
    assert not result['regulatory_evidence']


def test_no_arbitrary_section_values():
    with pytest.raises(ValidationError):
        SponsorClaim(case_id='test-id',drug_substance='Ibuprofen',s4_fields={'3.2.S.2':{}})


def test_load_cases_rejects_claimed_expert_labels(tmp_path):
    f=tmp_path/'cases.json'
    f.write_text(json.dumps({'label_status':'EXPERT_APPROVED','cases':[{'case_id':'one','drug_substance':'Ibuprofen'}]}))
    with pytest.raises(ValueError):load_cases(f)


def proposal(**updates):
    values={'source_id':'WHO-IBU-2025','title':'Ibuprofen','substance':'Ibuprofen',
            'compendium':'Ph.Int.','edition':'WHO 2025','official_source_url':'https://digicollections.net/phint/',
            'pdf_sha256':'0'*64,'license_review_reference':'permission-record','reviewer_id':'M5',
            'reviewer_basis':'Reviewed permitted use and relevant version',
            'applicable_product_scope':'DRUG_SUBSTANCE_CHEMICAL'}
    values.update(updates)
    return ReviewedSourceProposal.model_validate(values)


def test_official_host_only():
    with pytest.raises(ValidationError):proposal(official_source_url='https://webofpharma.com/fake.pdf')
    with pytest.raises(ValidationError):proposal(official_source_url='http://digicollections.net/phint/')


def test_cannot_self_approve():
    with pytest.raises(ValidationError):proposal(approval_decision='APPROVED')


def test_invalid_edition_interval():
    with pytest.raises(ValidationError):proposal(effective_from=date(2026,1,1),effective_to=date(2025,1,1))


def test_candidate_hash_and_substance_verified(tmp_path):
    import hashlib
    pdf=tmp_path/'m.pdf';doc=fitz.open();p=doc.new_page();p.insert_text((50,50),'Ibuprofen monograph research test - not actual standard');doc.save(pdf);doc.close()
    digest=hashlib.sha256(pdf.read_bytes()).hexdigest()
    p=proposal(pdf_sha256=digest)
    result=inspect_candidate(p,pdf)
    assert result['sha256_verified']
    assert not result['publish_to_regulatory_index']
    assert result['approval_decision'] is None
    staged=stage_submission(p,pdf,tmp_path/'receipts')
    assert staged['intake_status'].endswith('EXTERNAL_REVIEW')
    assert (tmp_path/'receipts'/'WHO-IBU-2025.staged.json').exists()


def test_reject_hash_mismatch_and_wrong_substance(tmp_path):
    import hashlib
    pdf=tmp_path/'m.pdf';d=fitz.open();page=d.new_page();page.insert_text((50,50),'Paracetamol is not ibuprofen');d.save(pdf);d.close()
    with pytest.raises(ValueError,match='SHA256'):
        inspect_candidate(proposal(),pdf)
    digest=hashlib.sha256(pdf.read_bytes()).hexdigest()
    # Name appears in this fixture, so replace with a true mismatch.
    d=fitz.open();page=d.new_page();page.insert_text((50,50),'Metronidazole test substance');d.save(pdf,incremental=False);d.close()
    digest=hashlib.sha256(pdf.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='substance name'):
        inspect_candidate(proposal(pdf_sha256=digest),pdf)


def test_m1_m5_api_endpoint_demo(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from m2.api import router, set_runtime
    from m2.runtime import M2Runtime,AppConfig
    from m2.runtime import AppConfig
    # Pre-existing fixture does not provide authoritative evidence. The route is a metadata-only handoff.
    monkeypatch.setenv('M2_PHINT_CATALOGUE',str(CAT))
    from m2.runtime import M2Runtime
    from m2.runtime import AppConfig
    cfg=AppConfig.from_file(str(ROOT/'config/default.json'))
    demo=M2Runtime(cfg)
    set_runtime(demo)
    app=FastAPI();app.include_router(router)
    client=TestClient(app)
    r=client.post('/m2/compendia/deferred-assessment',json={
        'case_id':'TEST-INTEGRATION','drug_substance':'Ibuprofen','cas':'15687-27-1',
        'claimed_compendium':'BP', 'product_type':'CHEMICAL'})
    assert r.status_code==200,r.text
    data=r.json()
    assert data['qa_status']=='PENDING'
    assert data['regulatory_evidence']==[]
    assert data['drug_authorisation_decision'] is None
    assert data['requires_human_review']
