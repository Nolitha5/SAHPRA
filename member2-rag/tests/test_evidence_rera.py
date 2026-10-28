"""Evidence/RERA agent: finding structure, insufficient evidence, provenance, conflicts."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.agents.evidence_rera import EvidenceReraAgent
from app.knowledge_base.indexing import index_records, parse_records
from app.retrieval.retrieval_service import RetrievalService
from app.schemas import (
    AgentRequest,
    Citation,
    EvidenceStatus,
    Finding,
    QAStatus,
    SponsorEvidence,
)
from tests.conftest import FakeReranker, make_record


def _real_looking_store(store, embedder, records):
    index_records(parse_records(json.dumps(r) for r in records).records, store, embedder)
    return store


def test_finding_structure_and_citations(service):
    finding = EvidenceReraAgent(service).assess("validation of analytical procedures", "3.2.S.4.3")
    assert isinstance(finding, Finding)
    assert finding.agent_name == "evidence_rera" and finding.ctd_section == "3.2.S.4.3"
    assert finding.evidence_status == EvidenceStatus.CANDIDATE_EVIDENCE_FOUND
    assert finding.regulatory_evidence
    assert {c.chunk_id for c in finding.citations} == {p.chunk_id for p in finding.regulatory_evidence}
    for cit, p in zip(finding.citations, finding.regulatory_evidence, strict=True):
        assert cit.source_identifier == p.metadata.source_identifier
        assert cit.page_number == p.metadata.page_number
        assert cit.content_hash == p.metadata.content_hash
    assert finding.requires_human_review
    assert "not a compliance determination" in finding.conclusion
    assert finding.qa_status != QAStatus.VERIFIED
    json.dumps(finding.model_dump(mode="json"))


def test_synthetic_data_forces_human_review(service):
    finding = EvidenceReraAgent(service).assess("validation of analytical procedures", "3.2.S.4.3")
    assert finding.qa_status == QAStatus.HUMAN_REVIEW
    assert "synthetic_test_data_not_real_evidence" in finding.metadata["flags"]


def test_real_type_current_source_gives_partial_not_verified(store, embedder, settings):
    _real_looking_store(store, embedder, [
        make_record(chunk_id="g1", document_type="guideline", ctd_section="3.2.S.4.3",
                    text="validation of analytical procedures accuracy precision"),
    ])
    svc = RetrievalService(store, embedder, FakeReranker(), settings)
    finding = EvidenceReraAgent(svc).assess("validation of analytical procedures", "3.2.S.4.3")
    assert finding.qa_status == QAStatus.PARTIAL
    assert finding.metadata["flags"] == []


def test_empty_knowledge_base(empty_service):
    finding = EvidenceReraAgent(empty_service).assess("any question", "3.2.S.4")
    assert finding.evidence_status == EvidenceStatus.EMPTY_KNOWLEDGE_BASE
    assert finding.qa_status == QAStatus.UNSUPPORTED
    assert finding.conclusion.startswith("Insufficient evidence")
    assert "does not prove" in finding.uncertainty
    assert finding.regulatory_evidence == [] and finding.citations == []


def test_no_passages_retrieved_vs_not_relevant(service, settings):
    from app.schemas import SearchFilters

    agent = EvidenceReraAgent(service)

    none = agent.assess("container closure", "3.2.S.6",
                        filters=SearchFilters(ctd_sections=["3.2.S.6"], include_parent_sections=False))
    assert none.evidence_status == EvidenceStatus.NO_PASSAGES_RETRIEVED
    assert none.qa_status == QAStatus.UNSUPPORTED
    assert "does not prove" in none.uncertainty


    weak = agent.assess("zebra giraffe elephant", "3.2.S.4")
    assert weak.evidence_status == EvidenceStatus.RETRIEVED_NOT_RELEVANT
    assert weak.qa_status == QAStatus.HUMAN_REVIEW
    assert weak.regulatory_evidence == []
    assert weak.metadata["below_threshold_candidates"]
    assert weak.conclusion.startswith("Insufficient evidence")


def test_version_conflict_and_superseded(store, embedder, settings):
    _real_looking_store(store, embedder, [
        make_record(chunk_id="v2", document_type="guideline", document_version="2.0",
                    text="validation analytical procedures new"),
        make_record(chunk_id="v1", document_type="guideline", document_version="1.0",
                    applicability_status="superseded", page_number=9,
                    text="validation analytical procedures old"),
    ])
    svc = RetrievalService(store, embedder, FakeReranker(), settings)
    finding = EvidenceReraAgent(svc).assess("validation analytical procedures", "3.2.S.4.1")
    assert finding.qa_status == QAStatus.CONFLICTING
    assert "multiple_versions_of_same_document" in finding.metadata["flags"]
    assert "contains_superseded_or_withdrawn_source" in finding.metadata["flags"]
    assert finding.metadata["version_conflicts"]


def test_incomplete_provenance_flagged(store, embedder, settings):
    _real_looking_store(store, embedder, [
        make_record(chunk_id="np", document_type="guideline", document_version=None, page_number=None,
                    publication_date=None, text="specification acceptance criteria"),
    ])
    svc = RetrievalService(store, embedder, FakeReranker(), settings)
    finding = EvidenceReraAgent(svc).assess("specification acceptance criteria", "3.2.S.4.1")
    assert "incomplete_provenance_for_some_sources" in finding.metadata["flags"]
    cit = finding.citations[0]
    assert cit.provenance_complete is False and cit.document_version is None and cit.page_number is None


def test_finding_rejects_invented_citation(service):
    finding = EvidenceReraAgent(service).assess("validation of analytical procedures", "3.2.S.4.3")
    fake = finding.citations[0].model_copy(update={"chunk_id": "invented-id"})
    data = finding.model_dump()
    data["citations"] = [fake.model_dump()]
    with pytest.raises(ValidationError, match="not in regulatory_evidence"):
        Finding(**data)


def test_evidence_without_citation_rejected(service):
    finding = EvidenceReraAgent(service).assess("validation of analytical procedures", "3.2.S.4.3")
    data = finding.model_dump()
    data["citations"] = []
    with pytest.raises(ValidationError, match="without citations"):
        Finding(**data)


def test_sponsor_evidence_kept_separate_and_redacted(service):
    secret = "CONFIDENTIAL batch 123 impurity 0.07%"
    sponsor = [SponsorEvidence(evidence_id="SP-1", ctd_section="3.2.S.4.4", content=secret)]
    finding = EvidenceReraAgent(service).assess("batch analyses", "3.2.S.4.4", sponsor_evidence=sponsor)
    assert finding.sponsor_evidence[0].content == secret
    assert all(secret not in p.text for p in finding.regulatory_evidence)
    assert secret not in repr(finding.sponsor_evidence[0])
    assert secret not in json.dumps(finding.model_dump_redacted())


def test_run_interface(service):
    req = AgentRequest(ctd_section="3.2.s.4.3", assessment_question="validation of analytical procedures")
    findings = EvidenceReraAgent(service).run(req)
    assert len(findings) == 1 and findings[0].ctd_section == "3.2.S.4.3"


def test_invalid_section_rejected(service):
    with pytest.raises(ValueError):
        EvidenceReraAgent(service).assess("question", "not-a-section")


def test_citation_label():
    from app.schemas import PassageRecord

    meta = PassageRecord(**make_record()).to_metadata()
    assert Citation.from_metadata(meta).short_label() == "TEST, Synthetic Test Guideline A, version 1.0, p.3"

    meta = PassageRecord(**make_record(document_version="Final Version (Step 4)")).to_metadata()
    assert Citation.from_metadata(meta).short_label() == "TEST, Synthetic Test Guideline A, Final Version (Step 4), p.3"


def test_source_summary_groups_pages_per_document():
    from app.agents.common import source_summary
    from app.schemas import PassageRecord, RetrievedPassage

    def passage(page, **kw):
        meta = PassageRecord(**make_record(chunk_id=f"c{page}", page_number=page, **kw)).to_metadata()
        return RetrievedPassage(chunk_id=meta.chunk_id, text="t", metadata=meta)

    summary = source_summary([passage(18), passage(7), passage(7), passage(2, source_title="Other")])
    assert summary == ("TEST, Synthetic Test Guideline A, version 1.0, pp. 7, 18; "
                       "TEST, Other, version 1.0, p. 2")


def test_integration_factory_builds_both_agents(tmp_path):
    from app.config import Settings
    from app.integration import create_member2_components

    m2 = create_member2_components(Settings(chroma_dir=tmp_path, collection_name="int_kb", log_json=False))
    assert set(m2.agents) == {"evidence_rera", "s4_control"}
    assert all(agent.retrieval is m2.retrieval for agent in m2.agents.values())
    assert m2.retrieval.store.count() == 0
