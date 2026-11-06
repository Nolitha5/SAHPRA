"""Integration checks against actual user-provided regulator-authored source PDFs."""
import json
from pathlib import Path
from m2.real_corpus import hash_file, preview_query

ROOT=Path(__file__).resolve().parents[1]

def test_all_real_uploads_indexed_with_sha():
    meta=json.loads((ROOT/'artifacts/real_corpus/REAL_CORPUS_MANIFEST.json').read_text(encoding='utf-8'))
    assert meta['unique_document_count']==15
    assert meta['indexed_chunk_count']>100
    assert meta['index_complete'] and not meta['expert_validated']
    for src in meta['sources']:
        assert src['page_count']>10
        assert src['sha256']==hash_file((ROOT/'regulatory_sources/user_supplied_unapproved'/src['pdf_file'] if (ROOT/'regulatory_sources/user_supplied_unapproved'/src['pdf_file']).exists() else ROOT/'regulatory_sources/additional_unapproved'/src['pdf_file']))

def test_real_m4q_s4_retrieval_and_page_anchor():
    result=preview_query(ROOT/'artifacts/real_corpus','3.2.S.4.3 validation analytical procedures',top_k=5,code='M4Q(R1)')
    match=next(x for x in result['evidence'] if x['source_id']=='ICH-M4Q-R1' and x['original_pdf_page']==16)
    assert 'analytical' in match['text'].lower()
    assert not match['regulatory_approved']

def test_real_who_and_ich_document_filter():
    out=preview_query(ROOT/'artifacts/real_corpus','active pharmaceutical ingredient long-term stability testing',code='TRS 1010 Annex 10')
    assert out['status']=='PREVIEW_MATCH'
    assert all(s['source_id']=='WHO-TRS1010-A10' for s in out['evidence'])
