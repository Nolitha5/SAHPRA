"""Offline reproducible checks for gated acquisition, pilot, labels and Chroma adapter."""
import json, sys, types
from pathlib import Path
import pytest
from m2.source_acquisition import catalogue,acquire_official_pdf,save_catalogue
from m2.chroma_validation import validate_chroma
from m2.label_governance import template,assess_labels
from m2.readiness import readiness
from m2.team_simulation import simulate_team, qa_critic_stub, SyntheticM4Audit
from m2.schemas import Finding, FindingStatus
from m2.embeddings import HashEmbedder
from m2.storage import ChromaVectorStore
from m2.schemas import RegulatoryChunk

ROOT=Path(__file__).resolve().parents[1]


def test_catalogue_unapproved_and_three_publishers(tmp_path):
    items=catalogue()
    assert {'SAHPRA','ICH','WHO'} <= {x['authority'] for x in items}
    assert not any(x['source_approved'] for x in items)
    p=save_catalogue(tmp_path/'catalog.json')
    assert json.loads(p.read_text())['status']=='DISCOVERY_ONLY_NOT_A_VERIFIED_INDEX'


def test_unverified_direct_pdf_cannot_be_guessed(tmp_path):
    with pytest.raises(ValueError,match='not independently verified'):
        acquire_official_pdf('ICH-Q6A',tmp_path)


def test_unknown_source_rejected(tmp_path):
    with pytest.raises(ValueError,match='Unknown source'):
        acquire_official_pdf('bad',tmp_path)


def test_acquire_pdf_requires_review(tmp_path):
    import fitz
    doc=fitz.open();p=doc.new_page();p.insert_text((72,72),'ICH Q11 Test PDF - local fixture');buf=doc.tobytes();doc.close()
    class FakeResponse:
        url='https://database.ich.org/sites/default/files/Q11_Guideline.pdf'
        history=[]
        def raise_for_status(self):pass
        def iter_content(self,chunk_size):yield buf
        def close(self):pass
    class Session:
        def get(self,*args,**kw):return FakeResponse()
    info=acquire_official_pdf('ICH-Q11',tmp_path,session=Session())
    assert info['pdf_pages']==1
    assert info['source_approved'] is False
    assert info['provenance_verified'] is False
    assert (tmp_path/'ICH-Q11.pdf').exists()
    with pytest.raises(FileExistsError):acquire_official_pdf('ICH-Q11',tmp_path,session=Session())


def test_foreign_redirect_rejected(tmp_path):
    class R:
        url='https://untrusted.example.org/payload.pdf';history=[]
        def raise_for_status(self):pass
        def close(self):pass
    class S:
        def get(self,*a,**kw):return R()
    with pytest.raises(ValueError,match='outside approved'):
        acquire_official_pdf('ICH-Q11',tmp_path,session=S())


def test_expert_template_does_not_attest_labels(tmp_path):
    t=template(tmp_path/'labels.json')
    d=json.loads(t.read_text());assert not d['review_records']
    status=assess_labels(t,tmp_path/'registry.json',tmp_path)
    assert status['status']=='NOT_EXPERT_VERIFIED'
    assert status['source_issues']


def test_readiness_fail_closed():
    result=readiness(ROOT)
    assert result['external_verification_required'] is True
    assert result['status']=='NOT_READY_FOR_AUTHORISED_PILOT'


def test_synthetic_team_handoff_sqlite(tmp_path):
    result=simulate_team(ROOT,tmp_path)
    assert result['execution_type']=='SYNTHETIC_FIVE_MEMBER_CONTRACT_SIMULATION'
    assert result['not_a_regulatory_pilot'] is True
    assert result['human_decision']=='NO_AUTHORISED_HUMAN_DECISION'
    assert result['m2_evidence_is_synthetic'] is True
    assert result['m2_s4_finding_count']>=5
    assert (tmp_path/'synthetic_case_audit.sqlite3').stat().st_size>0


def test_stub_qa_flags_absent_citations():
    f=Finding(finding_id='f1',case_id='c',agent_id='S4',ctd_section='3.2.S.4.3',
              issue_type='gap',status=FindingStatus.INSUFFICIENT_EVIDENCE,
              rationale='Insufficient evidence',uncertainty=1.0)
    result=qa_critic_stub([f]);assert result[0].qa_status.value=='FLAG'
    assert result[0].requires_human_review


def test_chroma_report_explicit_when_absent():
    import importlib.util
    if importlib.util.find_spec('chromadb') is None:
        result=validate_chroma()
        assert result['status']=='BLOCKED'
        assert not result['tests']


class _FakeCollection:
    def __init__(self): self.rows={}
    def upsert(self,ids,embeddings,documents,metadatas):
        for i,v,d,m in zip(ids,embeddings,documents,metadatas):self.rows[i]=(v,d,m)
    def count(self):return len(self.rows)
    def get(self,offset,limit,include):
        return {'metadatas':[v[2] for v in list(self.rows.values())[offset:offset+limit]]}
    def query(self,query_embeddings,n_results,include):
        import numpy as np
        q=np.array(query_embeddings[0]); sorted_rows=sorted(self.rows.values(),key=lambda x:-np.dot(q,x[0]))[:n_results]
        return {'metadatas':[[x[2] for x in sorted_rows]],'distances':[[max(0,1-float(np.dot(q,x[0]))) for x in sorted_rows]]}


def test_chroma_adapter_interface_mock_not_native(monkeypatch,tmp_path):
    """Contract unit test only; genuine Chroma runtime is checked separately."""
    pools={}
    class FakeClient:
        def __init__(self,path):self.path=path
        def get_or_create_collection(self,name,metadata):return pools.setdefault((self.path,name),_FakeCollection())
    monkeypatch.setitem(sys.modules,'chromadb',types.SimpleNamespace(PersistentClient=FakeClient))
    e=HashEmbedder()
    store=ChromaVectorStore(e,str(tmp_path))
    chunk=RegulatoryChunk(chunk_id='unit-c',source_id='UNIT',text='assay accuracy test',section='3.2.S.4.3')
    store.upsert([chunk]);assert store.count()==1
    reopened=ChromaVectorStore(e,str(tmp_path))
    assert reopened.count()==1
    assert reopened.all_chunks()[0].chunk_id=='unit-c'
    assert reopened.search('assay accuracy',1)[0][0].chunk_id=='unit-c'


def test_real_sqlite_persistence_offline(tmp_path):
    from m2.sqlite_vectors import SQLiteVectorStore
    from m2.embeddings import HashEmbedder
    embedder=HashEmbedder()
    db=tmp_path/'actual.sqlite3'
    c=RegulatoryChunk(chunk_id='persist-1',source_id='SYNTHETIC',
        text='synthetic batch assays accuracy precision',section='3.2.S.4.4',page=2)
    a=SQLiteVectorStore(embedder,db)
    a.upsert([c]);assert a.count()==1
    a.close()
    b=SQLiteVectorStore(embedder,db)
    assert b.count()==1
    assert b.search('batch assays accuracy',1)[0][0].chunk_id=='persist-1'
    b.close()


def test_research_sqlite_fallback_rejected(tmp_path):
    from m2.runtime import M2Runtime, AppConfig
    with pytest.raises(ValueError,match='fallback'):
        M2Runtime(AppConfig(mode='research',backend='sqlite',embedding_model='BAAI/bge-large-en-v1.5',
                            index_path=str(tmp_path/'db.sqlite3')))
