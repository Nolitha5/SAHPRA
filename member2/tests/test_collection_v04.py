"""Checks for acquisition/index release: no silent approval or fake coverage."""
from pathlib import Path
import sys
import json
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from collect_validate_index import inspect_source,run,ROOT,QUEUE

def test_q11_is_present_real_pdf_not_approved():
    s={'source_id':'ICH-Q11','document_code':'Q11','filename':'ICH-Q11.pdf'}
    out=inspect_source(s,ROOT/'regulatory_sources/user_supplied_unapproved/ICH-Q11.pdf')
    assert out['status']=='EXTRACTABLE_PDF_TECHNICAL_ONLY'
    assert out['pages']>=20
    assert out['regulatory_approved'] is False

def test_missing_cannot_be_present():
    out=inspect_source({'source_id':'X','document_code':'Q6A','filename':'X.pdf'},ROOT/'regulatory_sources/none/X.pdf')
    assert out['status']=='MISSING'

def test_nonpdf_is_rejected(tmp_path):
    path=tmp_path/'fake.pdf';path.write_bytes(b'<html>'+b'a'*5000)
    out=inspect_source({'source_id':'X','document_code':'Q6A','filename':'fake.pdf'},path)
    assert out['status']=='REJECT_NON_PDF_OR_TRUNCATED'

def test_official_download_manifest_distinguishes_missing():
    inventory=json.loads((ROOT/'regulatory_sources/REGULATORY_DOCUMENT_INVENTORY_v0.4.json').read_text())
    docs=inventory['documents']
    assert len(docs)==15
    assert sum(d['file_in_zip'] for d in docs)==3  # v0.4 snapshot remains unchanged for traceability
    assert not inventory['assessor_approved']

def test_queue_has_unique_ids_https_and_no_approved():
    q=json.loads(QUEUE.read_text())['sources']
    assert len({s['source_id'] for s in q})==len(q)
    assert all(s['url'].startswith('https://') for s in q)
    assert all(s['review_status']=='PENDING_DOCUMENT_AND_DOMAIN_REVIEW' for s in q)

def test_status_mode_preserves_unapproved_state(tmp_path):
    r=run(report_path=tmp_path/'report.json')
    assert r['additional_present']==12
    assert r['all_sources_domain_approved'] is False
    assert r['download_performed'] is False
    assert json.loads((tmp_path/'report.json').read_text())['all_sources_domain_approved'] is False
