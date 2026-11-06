"""Integration tests with the REAL BGE models (downloads ~150 MB - 1.4 GB).

Skipped by default (see pytest.ini). Run with:
    pytest -m integration
Uses bge-small + bge-reranker-base to stay light; set M2_IT_EMBEDDING_MODEL to
test bge-large.
"""

from __future__ import annotations

import json
import os

import pytest

from app.config import Settings
from app.embeddings.bge_embeddings import BGEEmbeddings
from app.knowledge_base.document_store import ChromaDocumentStore
from app.knowledge_base.indexing import index_records, parse_records
from app.retrieval.reranker import BGEReranker
from app.retrieval.retrieval_service import RetrievalService
from tests.conftest import SYNTHETIC_CORPUS

pytestmark = pytest.mark.integration

MODEL = os.getenv("M2_IT_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")


@pytest.fixture(scope="module")
def real_embedder():
    return BGEEmbeddings(MODEL)


def test_embeddings_are_normalised(real_embedder):
    import numpy as np

    vec = np.array(real_embedder.embed_query("drug substance specification"))
    assert vec.shape == (real_embedder.dimension,)
    assert abs(np.linalg.norm(vec) - 1.0) < 1e-3


def test_end_to_end_retrieval_with_reranker(tmp_path, real_embedder):
    settings = Settings(chroma_dir=tmp_path, collection_name="it_kb", embedding_model=MODEL, final_k=3)
    store = ChromaDocumentStore(tmp_path, "it_kb", real_embedder.model_name, real_embedder.dimension)
    index_records(parse_records(json.dumps(r) for r in SYNTHETIC_CORPUS).records, store, real_embedder)
    service = RetrievalService(store, real_embedder, BGEReranker("BAAI/bge-reranker-base"), settings)
    result = service.retrieve("How is an analytical procedure validated?")
    assert result.passages[0].chunk_id == "syn-val-1"
    assert result.passages[0].rerank_score is not None
