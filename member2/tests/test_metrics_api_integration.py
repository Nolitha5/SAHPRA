import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from m2.schemas import GoldQuery
from m2.evaluation import retrieval_metrics,benchmark
from m2.integration import evidence_node,s4_node
from m2.api import router,set_runtime


def test_metrics():
    m=retrieval_metrics(['a','b','z'],['b'],3)
    assert abs(m['precision_at_k']-1/3)<1e-8
    assert m['recall_at_k']==1.0
    assert m['mrr_at_k']==0.5
    assert 0<m['ndcg_at_k']<1


def test_benchmark_export(demo,tmp_path):
    gold=[GoldQuery.model_validate(x) for x in json.loads(Path('examples/synthetic_gold.json').read_text())]
    report=benchmark(demo.evidence,gold,k=3)
    assert report.evaluated_queries==4
    assert set(report.aggregate)=={'precision_at_k','recall_at_k','mrr_at_k','ndcg_at_k'}
    assert 0<=report.aggregate['recall_at_k']<=1


def test_evidence_langgraph_adapter(demo):
    node=evidence_node(demo)
    out=node({'evidence_request':{'request_id':'test','requesting_agent':'S1_IDENTITY','question':'analytical validation accuracy precision'}})
    assert out['evidence_result']['status']=='FOUND'


def test_s4_langgraph_adapter(demo):
    node=s4_node(demo)
    out=node({'s4_request':json.loads(Path('examples/synthetic_s4_case.json').read_text())})
    assert len(out['findings'])==5
    assert out['findings'][0]['qa_status']=='PENDING'


def test_api_endpoints(demo):
    set_runtime(demo)
    local=FastAPI();local.include_router(router)
    client=TestClient(local)
    health=client.get('/m2/health')
    assert health.status_code==200 and health.json()['chunk_count']==6
    result=client.post('/m2/evidence',json={'request_id':'a','requesting_agent':'S5_REFERENCE_STANDARDS','question':'analytical validation accuracy precision'})
    assert result.status_code==200 and result.json()['status']=='FOUND'
    review=client.post('/m2/s4/review',json=json.loads(Path('examples/synthetic_s4_case.json').read_text()))
    assert review.status_code==200 and len(review.json()['findings'])==5


def test_api_bad_payload(demo):
    set_runtime(demo);local=FastAPI();local.include_router(router);client=TestClient(local)
    r=client.post('/m2/evidence',json={'request_id':'a','question':'a'})
    assert r.status_code==422


def test_source_anchored_benchmark_is_stable_across_chunk_ids(demo):
    from m2.experiments import anchored_benchmark,AnchoredGoldQuery,EvidenceAnchor
    queries=[AnchoredGoldQuery(query_id='q',question='analytical validation accuracy precision',
                               relevant=[EvidenceAnchor(source_id='SYNTHETIC-TEST-001',section='test-analytical-validation')])]
    report=anchored_benchmark(demo.evidence,queries,k=3)
    assert report['aggregate']['recall_at_k']==1.0


def test_ragas_handoff_requires_real_answer_and_reference(tmp_path):
    import pytest
    from m2.ragas_adapter import RagasHandoffRow,export_ragas_jsonl,evaluate_with_ragas
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        RagasHandoffRow(user_input='some question',retrieved_contexts=['passage'],response='',reference='',source_ids=['S1'])
    row=RagasHandoffRow(user_input='some question',retrieved_contexts=['passage'],response='generated answer',reference='human reference',source_ids=['S1'])
    out=tmp_path/'handoff.jsonl';export_ragas_jsonl([row],str(out))
    assert json.loads(out.read_text())['reference']=='human reference'
    with pytest.raises(ValueError):evaluate_with_ragas([row],judge_llm=None,embeddings=None)
