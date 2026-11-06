"""v0.6 tests. Source page probes remain engineer-authored, not expert labels."""
from __future__ import annotations
import json
from pathlib import Path
import pytest

from m2.technical_benchmark import (NavigationRanker,verify_chunks,verify_probes,
                                    evaluate_navigation,benchmark_from_files,source_pdf_map)
from m2.schemas import RegulatoryChunk

ROOT=Path(__file__).resolve().parents[1]

def test_source_probes_are_physically_anchored():
    m=json.loads((ROOT/'artifacts/real_corpus/REAL_CORPUS_MANIFEST.json').read_text())
    probes=json.loads((ROOT/'examples/researcher_navigation_probes_v0.6.json').read_text())['probes']
    enriched=verify_probes(ROOT,m,probes)
    assert len(enriched)==30
    assert len({p['expected_source_id'] for p in enriched})==15
    assert all(p['anchor_pdf_page']>0 for p in enriched)

def test_offline_benchmark_covers_all_sources_and_modes():
    r=benchmark_from_files(ROOT)
    assert r['query_count']==30
    assert r['chunk_count']==554
    assert len(r['models'])==5
    assert r['source_approvals_granted'] is False
    for mode,summary in r['models'].items():
        assert summary['count']==30
        assert 0<=summary['aggregate']['source_hit_at_5']<=1
        assert summary['research_status'].endswith('NOT_EXPERT_LABELS')

def test_verification_rejects_unknown_source_id():
    m=json.loads((ROOT/'artifacts/real_corpus/REAL_CORPUS_MANIFEST.json').read_text())
    bad=[dict(id='broken',expected_source_id='FAKE',question='some lengthy question',source_anchor_phrase='X')]
    with pytest.raises(ValueError, match='Unknown source'):
        verify_probes(ROOT,m,bad)

def test_index_does_not_allow_duplicate_chunk_id():
    m={'sources':[{'source_id':'T','page_count':2}],'indexed_chunk_count':2}
    chunk=RegulatoryChunk(chunk_id='dupe',source_id='T',text='testing',section='1',page=1)
    with pytest.raises(ValueError,match='Duplicate chunk'):
        verify_chunks([chunk,chunk],m)

def test_page_anchor_is_not_substituted_by_document_only_hit():
    probe=[{'id':'q','question':'x','expected_source_id':'SRC','anchor_pdf_page':9}]
    chunk=RegulatoryChunk(chunk_id='c',source_id='SRC',text='testing',section='1',page=3)
    scored=evaluate_navigation(probe,[[(chunk,0.8)]])
    assert scored['aggregate']['source_hit_at_1']==1
    assert scored['aggregate']['anchor_page_hit_at_5']==0

def test_native_preflight_never_falsely_reports_success():
    import importlib.util
    import runpy
    ns=runpy.run_path(str(ROOT/'scripts/run_native_bge_chroma_validation.py'),run_name='loaded_for_test')
    report=ns['preflight']()
    assert report['status'] in {'BLOCKED_MISSING_DEPENDENCIES','READY_TO_ATTEMPT'}
    assert report['packages']['chromadb']==(importlib.util.find_spec('chromadb') is not None)
