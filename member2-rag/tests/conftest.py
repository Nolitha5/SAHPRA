"""Shared pytest fixtures.

Unit tests never download a real model. They use:
* `FakeEmbedder` - deterministic bag-of-words hashing into a 64-dim vector,
  L2-normalised (so texts sharing words are "similar", like a real embedder).
* `FakeReranker` - scores by word overlap, so its ordering is predictable.

Every test gets its own temporary ChromaDB directory (`tmp_path`), so the
production database in data/chroma is never touched.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Sequence
from pathlib import Path

import pytest

from app.config import Settings
from app.knowledge_base.document_store import ChromaDocumentStore
from app.knowledge_base.indexing import index_records, parse_records
from app.retrieval.retrieval_service import RetrievalService

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class FakeEmbedder:
    def __init__(self, name: str = "fake-embedder", dim: int = 64) -> None:
        self._name = name
        self._dim = dim
        self.document_calls = 0
        self.query_calls = 0

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def dimension(self) -> int:
        return self._dim

    def _vec(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        for tok in _tokens(text):
            idx = int(hashlib.md5(tok.encode()).hexdigest(), 16) % self._dim
            vec[idx] += 1.0
        if not any(vec):
            vec[0] = 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec]

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.document_calls += len(texts)
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return self._vec(text)


class FakeReranker:
    model_name = "fake-reranker"

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        q = set(_tokens(query))

        return [len(q & set(_tokens(p))) - 0.5 for p in passages]


def make_record(**overrides) -> dict:
    """A complete, valid SYNTHETIC passage record (not real regulatory text)."""
    base = {
        "chunk_id": "syn-001",
        "text": "Synthetic test passage about drug substance specification tests and acceptance criteria.",
        "source_title": "Synthetic Test Guideline A",
        "issuing_organization": "TEST",
        "source_identifier": "SYNTH-GL-A",
        "document_version": "1.0",
        "publication_date": "2020-01-01",
        "page_number": 3,
        "ctd_section": "3.2.S.4.1",
        "document_type": "synthetic_test",
        "applicability_status": "current",
        "chunk_index": 0,
    }
    base.update(overrides)
    return base


SYNTHETIC_CORPUS = [
    make_record(
        chunk_id="syn-spec-1",
        text="Synthetic: the drug substance specification lists tests, analytical procedures and acceptance criteria.",
        ctd_section="3.2.S.4.1",
        page_number=1,
    ),
    make_record(
        chunk_id="syn-val-1",
        text="Synthetic: validation of analytical procedures covers specificity accuracy precision linearity range.",
        ctd_section="3.2.S.4.3",
        page_number=2,
    ),
    make_record(
        chunk_id="syn-batch-1",
        text="Synthetic: batch analyses results should be provided for representative batches of drug substance.",
        ctd_section="3.2.S.4.4",
        page_number=3,
    ),
    make_record(
        chunk_id="syn-stab-1",
        text="Synthetic: stability studies, storage conditions and retest period for the drug substance.",
        ctd_section="3.2.S.7",
        page_number=4,
    ),
    make_record(
        chunk_id="syn-gen-1",
        text="Synthetic: general information on drug substance nomenclature and structure.",
        ctd_section="3.2.S",
        page_number=5,
        source_identifier="SYNTH-GL-B",
        source_title="Synthetic Test Guideline B",
    ),
]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        chroma_dir=tmp_path / "chroma",
        collection_name="test_kb",
        embedding_model="fake-embedder",
        reranker_enabled=True,
        reranker_model="fake-reranker",
        candidate_k=10,
        final_k=3,
        min_rerank_score=0.0,
        min_retrieval_score=0.2,
        log_json=False,
    )


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def reranker() -> FakeReranker:
    return FakeReranker()


@pytest.fixture
def store(settings: Settings, embedder: FakeEmbedder) -> ChromaDocumentStore:
    return ChromaDocumentStore(
        settings.chroma_dir, settings.collection_name, embedder.model_name, embedder.dimension
    )


@pytest.fixture
def populated_store(store: ChromaDocumentStore, embedder: FakeEmbedder) -> ChromaDocumentStore:
    loaded = parse_records(json.dumps(r) for r in SYNTHETIC_CORPUS)
    assert not loaded.errors
    index_records(loaded.records, store, embedder)
    return store


@pytest.fixture
def service(populated_store, embedder, reranker, settings) -> RetrievalService:
    return RetrievalService(populated_store, embedder, reranker, settings)


@pytest.fixture
def empty_service(store, embedder, reranker, settings) -> RetrievalService:
    return RetrievalService(store, embedder, reranker, settings)


def write_jsonl(path: Path, rows: list) -> Path:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write((row if isinstance(row, str) else json.dumps(row)) + "\n")
    return path
