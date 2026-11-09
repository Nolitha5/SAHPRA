"""Automatic routing: search once, let the best passages vote for a CTD section, pick the agent."""

from __future__ import annotations

import hashlib

from app.agents.evidence_rera import EvidenceReraAgent
from app.agents.s4_control import S4ControlAgent
from app.integration import Member2Components
from app.retrieval.retrieval_service import RetrievalService
from app.routing import ask, choose_route
from app.schemas import PassageMetadata, RetrievalResult, RetrievedPassage, SearchFilters
from tests.conftest import FakeReranker, make_record
from tests.test_api import _client


def _components(store, embedder, settings) -> Member2Components:
    service = RetrievalService(store, embedder, FakeReranker(), settings)
    return Member2Components(settings=settings, retrieval=service, agents={
        "evidence_rera": EvidenceReraAgent(service, settings), "s4_control": S4ControlAgent(service, settings)})


def _result(tags_and_scores: list[tuple[str, float]]) -> RetrievalResult:
    passages = []
    for i, (tag, score) in enumerate(tags_and_scores):
        rec = make_record(chunk_id=f"c{i}", ctd_section=tag, page_number=i + 1, source_identifier=f"DOC-{i}")
        meta = PassageMetadata(**{k: v for k, v in rec.items() if k != "text"},
                               content_hash=hashlib.sha256(f"t{i}".encode()).hexdigest())
        passages.append(RetrievedPassage(chunk_id=f"c{i}", text="t", metadata=meta, retrieval_score=0.8,
                                         retrieval_rank=i + 1, rerank_score=score, rerank_rank=i + 1))
    return RetrievalResult(query_fingerprint="x", filters=SearchFilters(), knowledge_base_size=10,
                           candidates_considered=10, reranked=True, embedding_model="m", reranker_model="r",
                           passages=passages, latency_ms=1.0)


def test_best_passages_vote_for_the_section(settings):
    route = choose_route(_result([("3.2.S.4.3", 3.0), ("3.2.S.4.3", 2.0), ("3.2.S.7", 1.0)]), settings)
    assert (route.agent, route.ctd_section) == ("s4_control", "3.2.S.4.3")
    assert route.based_on[0].startswith("DOC-0 p.1 (3.2.S.4.3)")
    route = choose_route(_result([("3.2.S.7", 3.0), ("3.2.S.4.1", 2.0), ("3.2.S.7", 1.0)]), settings)
    assert (route.agent, route.ctd_section) == ("evidence_rera", "3.2.S.7")


def test_s4_family_wins_together_even_if_split_across_subsections(settings):
    # 3.2.S.3 is the single best tag, but S.4 subsections together outweigh it.
    route = choose_route(_result([("3.2.S.3", 3.0), ("3.2.S.4.1", 2.0), ("3.2.S.4", 1.5), ("3.2.S.4.2", 1.0)]),
                         settings)
    assert route.agent == "s4_control" and route.ctd_section.startswith("3.2.S.4")


def test_only_relevant_passages_vote_when_there_are_any(settings):
    # min_rerank_score is 0.0 in the test settings: the negative S.4 passages do not vote.
    route = choose_route(_result([("3.2.S.4.1", -1.0), ("3.2.S.4.1", -2.0), ("3.2.S.7", 0.5)]), settings)
    assert route.ctd_section == "3.2.S.7"


def test_nothing_found_goes_to_evidence_rera(settings):
    route = choose_route(_result([]), settings)
    assert (route.agent, route.ctd_section) == ("evidence_rera", "3.2")


def test_ask_routes_and_searches_only_once(populated_store, embedder, settings):
    m2 = _components(populated_store, embedder, settings)
    route, findings = ask(m2, "validation of analytical procedures specificity accuracy precision")
    assert route.agent == "s4_control" and route.ctd_section == "3.2.S.4.3"
    assert findings[0].agent_name == "s4_control" and findings[0].ctd_section == "3.2.S.4.3"
    assert embedder.query_calls == 1  # the agent reused the router's search

    route, findings = ask(m2, "stability studies storage conditions retest period")
    assert route.agent == "evidence_rera" and route.ctd_section == "3.2.S.7"
    assert findings[0].citations and findings[0].citations[0].ctd_section == "3.2.S.7"


def test_ask_on_an_empty_knowledge_base(store, embedder, settings):
    route, findings = ask(_components(store, embedder, settings), "anything at all")
    assert route.agent == "evidence_rera"
    assert findings[0].evidence_status.value == "empty_knowledge_base"


def test_ask_endpoint(settings, populated_store, embedder, tmp_path):
    client = _client(settings, populated_store, embedder, tmp_path=tmp_path)
    body = client.post("/api/ask", json={"question": "batch analyses results for representative batches"}).json()
    assert body["route"]["agent"] == "s4_control" and body["route"]["ctd_section"] == "3.2.S.4.4"
    assert body["findings"][0]["agent_name"] == "s4_control"
    assert client.post("/api/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/ask", json={"question": "x", "unknown": 1}).status_code == 422
