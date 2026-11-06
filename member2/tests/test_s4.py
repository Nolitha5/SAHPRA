import json
from pathlib import Path
from m2.schemas import S4ReviewRequest,FindingStatus,QAStatus,DossierChunk
from m2.s4 import S4ControlAgent


def test_returns_five_structured_findings(demo):
    req=S4ReviewRequest.model_validate_json(Path('examples/synthetic_s4_case.json').read_text())
    res=demo.s4.review(req)
    assert len(res.findings)==5
    assert {f.ctd_section for f in res.findings} == {'3.2.S.4.'+str(i) for i in range(1,6)}
    assert all(f.qa_status==QAStatus.PENDING and f.requires_human_review for f in res.findings)
    assert all(f.status==FindingStatus.REVIEW_REQUIRED for f in res.findings)
    assert all(f.sponsor_evidence and f.regulatory_evidence for f in res.findings)


def test_missing_section_requests_review_not_noncompliance(demo):
    res=demo.s4.review(S4ReviewRequest(case_id='missing',dossier_chunks=[]))
    assert all(f.status==FindingStatus.MISSING_INFORMATION for f in res.findings)
    assert all('Verify dossier completeness' in f.rationale for f in res.findings)


def test_failed_retrieval_not_imputed(demo):
    demo.evidence.config.allow_synthetic=False
    req=S4ReviewRequest.model_validate_json(Path('examples/synthetic_s4_case.json').read_text())
    res=demo.s4.review(req)
    assert all(f.status==FindingStatus.INSUFFICIENT_EVIDENCE for f in res.findings)
    assert all(not f.regulatory_evidence for f in res.findings)


def test_m3_structure_extraction_hints(demo):
    req=S4ReviewRequest.model_validate_json(Path('examples/synthetic_s4_case.json').read_text())
    fields=demo.s4.extract_s4_fields(req.dossier_chunks)
    assert fields['limits'] and fields['validation'] and fields['batch_analyses']


def test_sponsor_quotes_not_invented(demo):
    req=S4ReviewRequest(case_id='c',dossier_chunks=[DossierChunk(chunk_id='d1',document_id='d',ctd_section='3.2.S.4.1',text='Only example specs')])
    res=demo.s4.review(req)
    first=res.findings[0]
    assert first.sponsor_evidence[0].passage=='Only example specs'
    assert first.qa_status==QAStatus.PENDING


def test_structured_sponsor_batch_outside_its_own_range_flagged(demo):
    from m2.s4_rules import compare_sponsor_batch_data
    chunks=[
        DossierChunk(chunk_id='spec1',document_id='d',ctd_section='3.2.S.4.1',text='Assay specification',table_rows=[{'test':'Assay','acceptance criteria':'98.0-102.0 %'}]),
        DossierChunk(chunk_id='batch1',document_id='d',ctd_section='3.2.S.4.4',text='Assay batch result',table_rows=[{'test':'Assay','result':'97.5 %'}])]
    observations=compare_sponsor_batch_data(chunks)
    assert len(observations)==1
    assert observations[0].data['observed']==97.5
    findings=demo.s4.review(S4ReviewRequest(case_id='batchcase',dossier_chunks=chunks)).findings
    assert any(f.issue_type=='SPONSOR_INTERNAL_NUMERIC_DISCREPANCY' and f.qa_status==QAStatus.PENDING for f in findings)


def test_units_mismatch_does_not_make_numerical_claim():
    from m2.s4_rules import compare_sponsor_batch_data
    chunks=[
        DossierChunk(chunk_id='s',document_id='d',ctd_section='3.2.S.4.1',text='spec',table_rows=[{'test':'Assay','limit':'98-102 %'}]),
        DossierChunk(chunk_id='b',document_id='d',ctd_section='3.2.S.4.4',text='batch',table_rows=[{'test':'Assay','result':'1 mg'}])]
    assert not compare_sponsor_batch_data(chunks)


def test_bad_quality_m3_extraction_cannot_be_assessed(demo):
    chunks=[DossierChunk(chunk_id='x',document_id='d',ctd_section='3.2.S.4.1',text='garbage specs',quality_flag='OCR_LOW_CONFIDENCE')]
    result=demo.s4.review(S4ReviewRequest(case_id='poor',dossier_chunks=chunks))
    assert result.findings[0].status==FindingStatus.MISSING_INFORMATION
