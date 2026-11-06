"""The v0.5 corpus is physically complete as an *unapproved technical preview*."""
from pathlib import Path
import json
import hashlib
import fitz
from m2.real_corpus import preview_query

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'artifacts/real_corpus'
INVENTORY=json.loads((ROOT/'regulatory_sources/REGULATORY_DOCUMENT_INVENTORY_v0.5.json').read_text())
MANIFEST=json.loads((INDEX/'REAL_CORPUS_MANIFEST.json').read_text())

def test_all_catalogued_15_physically_present_and_unique():
    assert INVENTORY['unique_documents']==INVENTORY['physically_included']==15
    hashes=[]
    for doc in INVENTORY['documents']:
        pdf=ROOT/doc['file']
        assert pdf.is_file() and pdf.read_bytes()[:5]==b'%PDF-'
        sha=hashlib.sha256(pdf.read_bytes()).hexdigest()
        assert doc['sha256']==sha
        hashes.append(sha)
        with fitz.open(pdf) as reader:assert reader.page_count==doc['pdf_pages']>0
        assert doc['regulatory_status']=='PENDING_DOMAIN_REVIEW'
    assert len(set(hashes))==15

def test_every_document_is_in_technical_index_and_review_gated():
    indexed={s['source_id'] for s in MANIFEST['sources']}
    all_ids={s['source_id'] for s in INVENTORY['documents']}
    assert indexed==all_ids
    assert MANIFEST['unique_document_count']==15
    assert MANIFEST['indexed_chunk_count']>=300
    assert not MANIFEST['expert_validated']
    assert MANIFEST['suitable_for_regulatory_decisions'] is False
    assert 'NOT ChromaDB' in MANIFEST['index_backend']
    assert 'NOT BGE' in MANIFEST['embedding_model']

def test_biologics_source_requires_product_scope_review():
    src=next(s for s in MANIFEST['sources'] if s['source_id']=='ICH-Q6B')
    assert src['source_group']=='conditional_biologics'
    assert src['requires_product_scope_review'] is True

def test_sahpra_v9_source_remains_pending_not_certified():
    doc=next(s for s in INVENTORY['documents'] if s['source_id']=='SAHPRA-PEM-02-V9')
    assert doc['regulatory_status']=='PENDING_DOMAIN_REVIEW'
    assert 'v8' in doc['notes'] and 'v9' in doc['notes']

def test_all_15_document_specific_preview_searches_have_page_and_source_anchor():
    queries=json.loads((ROOT/'examples/real_reference_queries_v0.5.json').read_text())['queries']
    sources={s['source_id']:s for s in MANIFEST['sources']}
    assert len(queries)==15
    for item in queries:
        sid=item['source_id']
        result=preview_query(INDEX,item['query'],code=sources[sid]['document_code'],top_k=2)
        assert result['status']=='PREVIEW_MATCH',sid
        assert result['preview_only'] is True
        assert all(x['source_id']==sid and x['original_pdf_page']>0 and not x['regulatory_approved'] for x in result['evidence']),sid

def test_no_evidence_is_not_fabricated():
    result=preview_query(INDEX,'purple kangaroo galaxies and rainbow pepper',code='NOT_A_REAL_GUIDELINE')
    assert result['status']=='NO_PREVIEW_MATCH'
    assert result['evidence']==[]
    assert result['human_review_required']
