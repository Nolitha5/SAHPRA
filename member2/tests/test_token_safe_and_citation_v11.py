"""Member 2 v1.1 release regression: exact source spans and token-safe indexing."""
import re
from pathlib import Path
import pytest
from m2.schemas import RegulatoryChunk
from m2.token_safe_index import TokenIndexConfig, split_regulatory_chunks
from m2.citation_audit import audit_pdf_passages

ROOT=Path(__file__).resolve().parents[1]

class FastWhitespaceTokenizer:
    is_fast=True
    def __call__(self,text,**kwargs):
        return {'offset_mapping':[(m.start(),m.end()) for m in re.finditer(r'\S+',text)]}


def parent(text='one two three four five six seven eight nine ten eleven twelve'):
    return RegulatoryChunk(chunk_id='test-001',source_id='ICH-M4Q-R1',
                           text=text,page=16,section='3.2.S.4.3')


def cfg(**kw):
    return TokenIndexConfig(model_id='TEST/tokenizer',max_model_tokens=16,
                            window_tokens=8,overlap_tokens=2,reserved_tokens=2,**kw)

def test_exact_substrings_and_overlaps():
    input_chunk=parent()
    out,report=split_regulatory_chunks([input_chunk],FastWhitespaceTokenizer(),cfg())
    assert len(out)==2
    assert out[0].text in input_chunk.text and out[1].text in input_chunk.text
    assert out[0].text.split()[-2:]==out[1].text.split()[:2]
    assert report['page_anchors_preserved']
    assert all(c.source_id==input_chunk.source_id and c.page==16 for c in out)
    assert all(c.metadata['parent_chunk_id']=='test-001' for c in out)
    assert report['indexed_chunks']==2

def test_deterministic_hashes():
    x=split_regulatory_chunks([parent()],FastWhitespaceTokenizer(),cfg())[0]
    y=split_regulatory_chunks([parent()],FastWhitespaceTokenizer(),cfg())[0]
    assert [c.chunk_id for c in x]==[c.chunk_id for c in y]

def test_rejects_non_fast_tokenizers():
    class Slow(FastWhitespaceTokenizer): is_fast=False
    with pytest.raises(RuntimeError,match='fast tokenizer'):
        split_regulatory_chunks([parent()],Slow(),cfg())

def test_rejects_unanchored_input():
    with pytest.raises(ValueError,match='Unanchored'):
        split_regulatory_chunks([RegulatoryChunk(chunk_id='X',source_id='S',section='1',
                                                 page=None,text='hello world')],FastWhitespaceTokenizer(),cfg())

def test_rejects_unsafe_window_config():
    with pytest.raises(ValueError,match='exceed model limit'):
        TokenIndexConfig(model_id='x',max_model_tokens=16,window_tokens=15,overlap_tokens=0,reserved_tokens=2)

def test_rejects_bad_overlaps():
    with pytest.raises(ValueError,match='Overlap'):
        TokenIndexConfig(model_id='x',max_model_tokens=32,window_tokens=16,overlap_tokens=16,reserved_tokens=2)

def test_bad_offset_detected():
    class Corrupted(FastWhitespaceTokenizer):
        def __call__(self,text,**kwargs):return {'offset_mapping':[(0,len(text)+5)]}
    with pytest.raises(ValueError,match='outside verified'):
        split_regulatory_chunks([parent()],Corrupted(),cfg())

def test_all_guideline_passages_match_original_page():
    report=audit_pdf_passages(ROOT)
    assert report['status']=='PASS_ANCHORED_TECHNICAL_AUDIT'
    assert report['pdfs_sha256_verified']==15
    assert report['passages_audited']==554
    assert report['unanchored_passages']==0
    assert not report['regulatory_decision_ready']
