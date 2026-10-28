"""Web API: reading, editing permissions, search, agents, benchmark, error hygiene."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.agents.evidence_rera import EvidenceReraAgent
from app.agents.s4_control import S4ControlAgent
from app.api.server import create_app
from app.integration import Member2Components
from app.retrieval.retrieval_service import RetrievalService
from tests.conftest import FakeReranker, make_record

TOKEN = "test-token-123456"


def _client(settings, store, embedder, token=TOKEN, tmp_path=None):
    settings = settings.with_overrides(
        admin_token=token,
        benchmark_file=tmp_path / "bench.jsonl",
        results_dir=tmp_path / "results",
        web_dist=tmp_path / "no-dist",
    )
    service = RetrievalService(store, embedder, FakeReranker(), settings)
    m2 = Member2Components(
        settings=settings,
        retrieval=service,
        agents={"evidence_rera": EvidenceReraAgent(service, settings), "s4_control": S4ControlAgent(service, settings)},
    )
    return TestClient(create_app(m2, settings))


@pytest.fixture
def client(settings, populated_store, embedder, tmp_path):
    return _client(settings, populated_store, embedder, tmp_path=tmp_path)


@pytest.fixture
def readonly_client(settings, populated_store, embedder, tmp_path):
    return _client(settings, populated_store, embedder, token="", tmp_path=tmp_path)


ADMIN = {"X-Admin-Token": TOKEN}



def test_health(client):
    data = client.get("/api/health").json()
    assert data["knowledge_base_size"] == 5
    assert data["editing_enabled"] is True
    assert data["reranker_model"]
    assert data["benchmark_file"].endswith(".jsonl")


def test_list_and_filter_passages(client):
    data = client.get("/api/passages", params={"limit": 2}).json()
    assert data["total"] == 5 and len(data["items"]) == 2
    first = data["items"][0]
    assert {"chunk_id", "text", "metadata", "provenance_complete", "missing_provenance"} <= set(first)
    s4 = client.get("/api/passages", params={"ctd_section": "3.2.S.4"}).json()
    assert {i["metadata"]["ctd_section"] for i in s4["items"]} == {"3.2.S.4.1", "3.2.S.4.3", "3.2.S.4.4"}
    assert client.get("/api/passages", params={"ctd_section": "nonsense"}).status_code == 422


def test_facets(client):
    facets = client.get("/api/passages/facets").json()
    assert facets["issuing_organization"] == {"TEST": 5}
    assert facets["ctd_section"]["3.2.S.4.1"] == 1



def test_writes_need_token(client):
    body = {"filename": "p.jsonl", "content": json.dumps(make_record(chunk_id="new-1"))}
    assert client.post("/api/passages/import", json=body).status_code == 401
    wrong = {"X-Admin-Token": "wrong-token-000"}
    assert client.post("/api/passages/import", json=body, headers=wrong).status_code == 401
    assert client.delete("/api/passages/syn-val-1").status_code == 401
    assert client.get("/api/health").json()["knowledge_base_size"] == 5


def test_writes_disabled_without_configured_token(readonly_client):
    r = readonly_client.delete("/api/passages/syn-val-1", headers={"X-Admin-Token": "anything-at-all"})
    assert r.status_code == 403 and "M2_ADMIN_TOKEN" in r.json()["detail"]


def test_import_dry_run_then_real(client):
    lines = "\n".join([json.dumps(make_record(chunk_id="new-1", text="Brand new passage")), "{broken"])
    dry = client.post("/api/passages/import", headers=ADMIN,
                      json={"filename": "p.jsonl", "content": lines, "dry_run": True}).json()
    assert dry["valid_records"] == 1 and dry["rejected"] == 1 and dry["added"] == 0
    real = client.post("/api/passages/import", headers=ADMIN, json={"filename": "p.jsonl", "content": lines}).json()
    assert real["added"] == 1 and real["total_in_collection"] == 6
    again = client.post("/api/passages/import", headers=ADMIN, json={"filename": "p.jsonl", "content": lines}).json()
    assert again["unchanged"] == 1


def test_import_rejects_wrong_type_and_empty(client):
    assert client.post("/api/passages/import", headers=ADMIN,
                       json={"filename": "x.csv", "content": "a,b"}).status_code == 422
    assert client.post("/api/passages/import", headers=ADMIN,
                       json={"filename": "x.jsonl", "content": "\n\n"}).status_code == 422


def test_delete_passage(client):
    assert client.delete("/api/passages/syn-val-1", headers=ADMIN).json()["knowledge_base_size"] == 4
    assert client.delete("/api/passages/syn-val-1", headers=ADMIN).status_code == 404



def test_search(client):
    data = client.post("/api/search", json={"query": "validation of analytical procedures",
                                            "filters": {"ctd_sections": ["3.2.S.4.3"]}}).json()
    assert data["passages"][0]["chunk_id"] == "syn-val-1"
    assert data["passages"][0]["rerank_score"] is not None
    assert data["reranked"] is True


def test_search_errors_do_not_echo_input(client):
    secret = "SECRET-QUESTION-" + "x" * 3000
    r = client.post("/api/search", json={"query": secret})
    assert r.status_code == 422 and "SECRET-QUESTION" not in r.text
    r = client.post("/api/search", json={"query": "ok", "bogus": "SECRET-FIELD"})
    assert r.status_code == 422 and "SECRET-FIELD" not in r.text


def test_evidence_agent_endpoint(client):
    r = client.post("/api/agents/evidence-rera", json={
        "ctd_section": "3.2.S.4.3", "assessment_question": "validation of analytical procedures"})
    findings = r.json()
    assert r.status_code == 200 and len(findings) == 1
    f = findings[0]
    assert f["agent_name"] == "evidence_rera" and f["citations"]
    assert f["qa_status"] != "verified"


def test_s4_agent_endpoint_with_example(client):
    from pathlib import Path

    example = json.loads((Path(__file__).parent.parent / "examples" / "s4_request.example.json").read_text())
    findings = client.post("/api/agents/s4-control", json=example).json()
    assert len(findings) == 2
    assert findings[1]["metadata"]["comparison_counts"]["within_criteria"] == 4
    assert findings[1]["metadata"]["confidential_comparison_rows"]


def test_s4_bad_parameters_return_400_without_values(client):
    r = client.post("/api/agents/s4-control", json={
        "ctd_section": "3.2.S.4.4", "assessment_question": "q",
        "parameters": {"batch_results": [{"batch_id": "B", "test_name": "T", "reported_value": "SECRET-9", "x": 1}]}})
    assert r.status_code == 400 and "SECRET-9" not in r.text


def test_empty_kb_agent(settings, store, embedder, tmp_path):
    c = _client(settings, store, embedder, tmp_path=tmp_path)
    f = c.post("/api/agents/evidence-rera", json={"ctd_section": "3.2.S.4", "assessment_question": "q"}).json()[0]
    assert f["evidence_status"] == "empty_knowledge_base" and f["conclusion"].startswith("Insufficient evidence")



def test_benchmark_cases_crud(client):
    assert client.get("/api/benchmark/cases").json() == []
    case = {"question_id": "Q1", "question": "Which tests belong in the specification?",
            "ctd_section": "3.2.S.4.1", "relevant_chunk_ids": ["syn-spec-1"]}
    assert client.post("/api/benchmark/cases", json=case).status_code == 401
    assert client.post("/api/benchmark/cases", json=case, headers=ADMIN).status_code == 201
    assert client.post("/api/benchmark/cases", json=case, headers=ADMIN).status_code == 409
    assert [c["question_id"] for c in client.get("/api/benchmark/cases").json()] == ["Q1"]
    bad = dict(case, question_id="Q2", relevant_chunk_ids=[])
    assert client.post("/api/benchmark/cases", json=bad, headers=ADMIN).status_code == 422
    assert client.delete("/api/benchmark/cases/Q1", headers=ADMIN).status_code == 200
    assert client.delete("/api/benchmark/cases/Q1", headers=ADMIN).status_code == 404


def test_benchmark_results_listing(client, tmp_path):
    results = tmp_path / "results"
    results.mkdir()
    (results / "retrieval_benchmark_20261014T100000Z.json").write_text(json.dumps({
        "created_at": "2026-10-14T10:00:00Z", "num_questions": 3, "benchmark_sha256": "abc",
        "benchmark_file": "C:\\somewhere\\benchmarks\\pilot.jsonl",
        "runs": [{"config": {"name": "large_reranked"}, "knowledge_base_size": 8,
                  "aggregate": {"mrr": 0.5}, "latency": {"p50_ms": 12}}]}))
    (results / "retrieval_benchmark_broken.json").write_text("{not json")
    data = client.get("/api/benchmark/results").json()
    assert len(data) == 1 and data[0]["runs"][0]["name"] == "large_reranked"
    assert data[0]["benchmark_file"] == "pilot.jsonl"
