from pathlib import Path
import json
import pytest
import fitz
from m2.real_corpus import index_uploaded, preview_query, hash_file, KNOWN

def test_real_pdf_index_query_traceability(tmp_path):
    sources={}
    for sid,code in [('ICH-M4Q-R1','M4Q'),('ICH-Q11','Q11'),('WHO-TRS1010-A10','Annex 10')]:
        path=tmp_path/(sid+'.pdf')
        doc=fitz.open()
        pg=doc.new_page()
        pg.insert_text((50,80),f'{code} Drug substance analytical validation procedures and batch analysis requirements. Stability testing data and specifications.')
        doc.save(path);doc.close();sources[sid]=path
    report=index_uploaded(sources,tmp_path/'idx',size=16,overlap=3)
    assert report['unique_document_count']==3
    assert report['indexed_chunk_count']>=3
    assert not report['expert_validated']
    result=preview_query(tmp_path/'idx','drug substance batch analysis',top_k=3)
    assert result['status']=='PREVIEW_MATCH'
    assert all(r['original_pdf_page'] == 1 for r in result['evidence'])
    assert all(not r['regulatory_approved'] for r in result['evidence'])
    result2=preview_query(tmp_path/'idx','batch analysis',code='Q11')
    assert all(r['document_code']=='Q11' for r in result2['evidence'])
    assert report['sources'][0]['sha256']==hash_file(sources['ICH-M4Q-R1'])

def test_source_missing_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):index_uploaded({'ICH-Q11':tmp_path/'missing.pdf'},tmp_path/'o')

def test_no_fabricated_passage(tmp_path):
    p=tmp_path/'Q11.pdf';d=fitz.open();pg=d.new_page();pg.insert_text((60,60),'Q11 '+'drug substance process control stability '*12);d.save(p);d.close()
    index_uploaded({'ICH-Q11':p},tmp_path/'i',size=64,overlap=8)
    out=preview_query(tmp_path/'i','zzznonexistentcryptword')
    assert out['evidence']==[]
    assert out['human_review_required']
