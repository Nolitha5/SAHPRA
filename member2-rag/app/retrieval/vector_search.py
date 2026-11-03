"""Semantic vector search over the ChromaDB knowledge base.

Steps:
1. Validate the query (non-empty, not too long).
2. Embed it with the BGE query instruction.
3. Translate `SearchFilters` into a ChromaDB `where` clause.
4. Return `RetrievedPassage` objects with original metadata and
   `retrieval_score` = cosine similarity (1 - cosine distance).

CTD filtering is hierarchical. Asking for "3.2.S.4" matches passages tagged
3.2.S.4 and any subsection (3.2.S.4.1 ... 3.2.S.4.5). With
`include_parent_sections=True` (default) it also matches passages tagged with
a parent heading such as "3.2.S", because general guidance is often mapped to
the parent heading by the ingestion pipeline.
"""

from __future__ import annotations

import re
from typing import Any

from app.embeddings.bge_embeddings import EmbeddingModel
from app.knowledge_base.document_store import ChromaDocumentStore
from app.knowledge_base.metadata import ctd_part
from app.schemas import RetrievedPassage, SearchFilters, ctd_ancestors


class InvalidQueryError(ValueError):
    """The query is empty, too long, or otherwise unusable."""


# Instruction-like text inside a *retrieved document* is suspicious: regulatory
# passages are evidence, never instructions. We flag (not delete) such text so
# downstream LLM components (Member 1/5) can treat it with extra caution.
_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (all |any )?(previous|prior|above) instructions",
        r"disregard (the )?(system|previous) (prompt|instructions)",
        r"you are now",
        r"system prompt",
        r"mark (this|the) (dossier|finding|application) as (compliant|verified|approved)",
    )
]


def detect_untrusted_instructions(text: str) -> list[str]:
    """Return labels for instruction-like patterns found in passage text."""
    return [f"instruction_like_text:{p.pattern}" for p in _INJECTION_PATTERNS if p.search(text)]


def validate_query(query: str, max_chars: int) -> str:
    if not isinstance(query, str):
        raise InvalidQueryError("query must be a string")
    cleaned = query.strip()
    if not cleaned:
        raise InvalidQueryError("query must not be empty")
    if len(cleaned) > max_chars:
        raise InvalidQueryError(f"query is too long ({len(cleaned)} > {max_chars} characters)")
    return cleaned


def _in(field: str, values: list[str]) -> dict[str, Any]:
    return {field: {"$in": values}} if len(values) > 1 else {field: values[0]}


def _combine(op: str, clauses: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {op: clauses}


def build_where(filters: SearchFilters | None) -> dict[str, Any] | None:
    """Translate `SearchFilters` into a ChromaDB `where` clause (or None)."""
    if filters is None or filters.is_empty():
        return None
    clauses: list[dict[str, Any]] = []

    if filters.ctd_sections:
        exact: set[str] = set()
        roots: set[str] = set()
        parts: set[str] = set()
        for section in filters.ctd_sections:
            exact.add(section)
            if section == ctd_part(section):
                parts.add(section)  # e.g. "3.2.S" -> everything in 3.2.S
            else:
                roots.add(section)  # subsections share this root
            if filters.include_parent_sections:
                exact.update(ctd_ancestors(section))
        ctd_clauses = [_in("ctd_section", sorted(exact))]
        if roots:
            ctd_clauses.append(_in("ctd_section_root", sorted(roots)))
        if parts:
            ctd_clauses.append(_in("ctd_part", sorted(parts)))
        combined = _combine("$or", ctd_clauses)
        if combined:
            clauses.append(combined)

    if filters.document_types:
        clauses.append(_in("document_type", [d.value for d in filters.document_types]))
    if filters.issuing_organizations:
        clauses.append(_in("issuing_organization", filters.issuing_organizations))
    if filters.applicability_statuses:
        clauses.append(_in("applicability_status", [s.value for s in filters.applicability_statuses]))

    return _combine("$and", clauses)


class VectorSearcher:
    """Embedding search against one ChromaDocumentStore."""

    def __init__(self, store: ChromaDocumentStore, embedder: EmbeddingModel, max_query_chars: int = 2000):
        if store.embedding_model_name != embedder.model_name:
            raise ValueError(
                f"Store is pinned to '{store.embedding_model_name}' but embedder is "
                f"'{embedder.model_name}'"
            )
        self.store = store
        self.embedder = embedder
        self.max_query_chars = max_query_chars

    def search(self, query: str, k: int, filters: SearchFilters | None = None) -> list[RetrievedPassage]:
        if k < 1:
            raise ValueError("k must be >= 1")
        cleaned = validate_query(query, self.max_query_chars)
        if self.store.count() == 0:
            return []
        vector = self.embedder.embed_query(cleaned)
        hits = self.store.query(vector, n_results=k, where=build_where(filters))
        return [
            RetrievedPassage(
                chunk_id=hit.chunk_id,
                text=hit.text,
                metadata=hit.metadata,
                retrieval_score=round(1.0 - hit.distance, 6),
                retrieval_rank=rank,
                untrusted_content_flags=detect_untrusted_instructions(hit.text),
            )
            for rank, hit in enumerate(hits, start=1)
        ]
