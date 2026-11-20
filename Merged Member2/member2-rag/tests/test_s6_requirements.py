"""M2 side of the S.6 Container Closure Agent's RequirementSource port (synthetic data only)."""

from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, ConfigDict

from app.adapters.s6_requirements import (
    S6RequirementSource,
    format_citation,
    requirements_from_passages,
    topic_to_question,
)
from app.knowledge_base.indexing import index_records, parse_records
from app.retrieval.retrieval_service import RetrievalService
from tests.conftest import make_record


# Copies of S.6's contract (branch thobeka-s6-container-closure, src/shared/models.py,
# commit of 2026-11-19), made strict so any field-name drift fails here.
class S6SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: str
    source_id: str
    section: str
    document: str | None = None
    page: int | None = None
    field_path: str | None = None


class S6RKBRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requirement_id: str
    guideline: str
    section: str
    text: str
    citation: str
    source_ref: S6SourceReference


CORPUS = [
    make_record(
        chunk_id="cc-desc",
        text="Synthetic: container closure system description, materials of construction of primary packaging "
             "components and their specifications.",
        ctd_section="3.2", source_identifier="SYNTH-M4", source_title="Synthetic M4 Guideline",
        page_number=19, page_label="11",
    ),
    make_record(
        chunk_id="cc-stab",
        text="Synthetic: stability studies in the container closure system proposed for storage and distribution "
             "of the drug substance.",
        ctd_section="3.2.S.7", source_identifier="SYNTH-STAB", source_title="Synthetic Stability Guideline",
        page_number=7,
    ),
    make_record(
        chunk_id="unrelated",
        text="Synthetic: validation of analytical procedures, specificity, accuracy, precision.",
        ctd_section="3.2.S.4.3", page_number=2,
    ),
]


@pytest.fixture
def cc_service(store, embedder, reranker, settings) -> RetrievalService:
    index_records(parse_records(json.dumps(r) for r in CORPUS).records, store, embedder)
    return RetrievalService(store, embedder, reranker, settings)


def test_topic_becomes_focused_question():
    q = topic_to_question("  glass   vial ")
    assert "glass vial" in q and "3.2.S.6" in q and q.endswith("?")
    assert topic_to_question("Is HDPE suitable?") == "Is HDPE suitable?"
    with pytest.raises(ValueError):
        topic_to_question("   ")


def test_output_matches_s6_contract_exactly(cc_service):
    rows = S6RequirementSource(cc_service).get_requirements("primary packaging components materials of construction")
    assert rows
    for row in rows:
        req = S6RKBRequirement.model_validate(row)  # extra="forbid": no unexpected fields
        assert req.source_ref.source_type == "m2_rkb"
        assert req.requirement_id == req.source_ref.source_id
    assert rows[0]["requirement_id"] == "cc-desc"
    assert rows[0]["guideline"] == "SYNTH-M4"
    assert rows[0]["source_ref"]["page"] == 19


def test_broadened_search_finds_guidance_tagged_outside_s6(cc_service):
    topic = "stability storage and distribution in the container closure system"
    broad = {r["requirement_id"] for r in S6RequirementSource(cc_service).get_requirements(topic)}
    narrow = {r["requirement_id"] for r in S6RequirementSource(cc_service, broaden=False).get_requirements(topic)}
    assert "cc-stab" in broad  # tagged 3.2.S.7: only the unfiltered search can return it
    assert "cc-stab" not in narrow


def test_no_duplicates_and_limit(cc_service):
    search = S6RequirementSource(cc_service, max_requirements=2).search("container closure system")
    ids = [r["requirement_id"] for r in search.requirements]
    assert len(ids) == len(set(ids)) <= 2
    assert set(search.scores) == set(ids)
    assert [s["search"] for s in search.searches] == ["ctd_3.2.S.6_with_parents", "all_guidelines"]


def test_weak_matches_are_not_returned_as_requirements(cc_service, settings):
    strict = settings.with_overrides(min_rerank_score=100.0)
    search = S6RequirementSource(cc_service, settings=strict).search("container closure system")
    assert search.requirements == []
    assert search.below_threshold > 0


def test_empty_knowledge_base_returns_empty_list(empty_service):
    search = S6RequirementSource(empty_service).search("glass vial")
    assert search.requirements == [] and search.knowledge_base_size == 0


def test_citation_has_printed_and_pdf_page(cc_service):
    result = cc_service.retrieve("container closure materials of construction")
    passage = next(p for p in result.passages if p.chunk_id == "cc-desc")
    assert format_citation(passage) == "SYNTH-M4 (1.0), p. 11 (PDF p. 19), CTD 3.2"
    assert requirements_from_passages([passage])[0]["citation"] == format_citation(passage)
