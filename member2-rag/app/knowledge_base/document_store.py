"""Persistent ChromaDB store for regulatory passages.

Responsibilities:
* Open/create a persistent collection configured for cosine distance.
* Pin the collection to ONE embedding model (name + dimension). Mixing vectors
  from different models in one collection silently breaks retrieval, so a
  mismatch raises an error instead.
* Upsert passages with duplicate handling:
    - same chunk_id + same content_hash  -> "unchanged" (skipped, no re-embed)
    - same chunk_id + different hash     -> "updated"
    - new chunk_id                       -> "added"
* Query by vector with optional metadata filters.

The store never embeds text itself; it receives vectors from an
`EmbeddingModel`. That keeps embedding models swappable for benchmarking.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.knowledge_base.metadata import from_chroma_metadata, to_chroma_metadata
from app.logging_utils import get_logger, log_event
from app.schemas import PassageMetadata

logger = get_logger("document_store")
_DIGITS = re.compile(r"(\d+)")


def natural_key(value: str) -> list[tuple[int, int | str]]:
    """Sort key that compares digit runs as numbers: 'p2' < 'p10'."""
    return [(0, int(part)) if part.isdigit() else (1, part) for part in _DIGITS.split(value) if part]


class EmbeddingModelMismatchError(RuntimeError):
    """The collection was built with a different embedding model."""


@dataclass
class StoredPassage:
    chunk_id: str
    text: str
    metadata: PassageMetadata


@dataclass
class QueryHit:
    chunk_id: str
    text: str
    metadata: PassageMetadata
    distance: float  # cosine distance in [0, 2]; similarity = 1 - distance


@dataclass
class UpsertReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    # Same text (same vector) but different metadata, e.g. a corrected page label:
    # the metadata is replaced without re-embedding.
    metadata_updated: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, int]:
        return {
            "added": len(self.added),
            "updated": len(self.updated),
            "unchanged": len(self.unchanged),
            "metadata_updated": len(self.metadata_updated),
        }


class ChromaDocumentStore:
    """Thin, validated wrapper around one ChromaDB collection."""

    def __init__(
        self,
        persist_dir: Path | str,
        collection_name: str,
        embedding_model_name: str,
        embedding_dimension: int | None = None,
    ) -> None:
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model_name
        self._client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=False),
        )
        metadata: dict[str, Any] = {"embedding_model": embedding_model_name}
        if embedding_dimension is not None:
            metadata["embedding_dimension"] = int(embedding_dimension)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            configuration={"hnsw": {"space": "cosine"}},
            metadata=metadata,
            embedding_function=None,  # we always pass our own vectors
        )
        self._check_model_pin(embedding_dimension)

    # ------------------------------------------------------------------
    def _check_model_pin(self, embedding_dimension: int | None) -> None:
        stored = self._collection.metadata or {}
        stored_model = stored.get("embedding_model")
        if stored_model and stored_model != self.embedding_model_name:
            raise EmbeddingModelMismatchError(
                f"Collection '{self.collection_name}' was built with '{stored_model}' but "
                f"'{self.embedding_model_name}' is configured. Use a different collection "
                "name (M2_COLLECTION_NAME) for each embedding model."
            )
        stored_dim = stored.get("embedding_dimension")
        if stored_dim is not None and embedding_dimension is not None and stored_dim != embedding_dimension:
            raise EmbeddingModelMismatchError(
                f"Collection '{self.collection_name}' stores {stored_dim}-dim vectors but the "
                f"embedder produces {embedding_dimension}-dim vectors."
            )

    # ------------------------------------------------------------------
    def count(self) -> int:
        return int(self._collection.count())

    def plan_upsert(self, items: Sequence[tuple[PassageMetadata, str]]) -> UpsertReport:
        """Classify items into added / updated (new text) / metadata_updated / unchanged."""
        report = UpsertReport()
        ids = [meta.chunk_id for meta, _ in items]
        result = self._collection.get(ids=ids, include=["metadatas"]) if ids else {"ids": [], "metadatas": []}
        existing = {cid: dict(m or {}) for cid, m in zip(result["ids"], result["metadatas"] or [], strict=True)}
        for meta, _ in items:
            stored = existing.get(meta.chunk_id)
            if stored is None:
                report.added.append(meta.chunk_id)
            elif stored.get("content_hash") != meta.content_hash:
                report.updated.append(meta.chunk_id)
            elif stored != to_chroma_metadata(meta, self.embedding_model_name):
                report.metadata_updated.append(meta.chunk_id)
            else:
                report.unchanged.append(meta.chunk_id)
        return report

    def replace_metadata(self, items: Sequence[tuple[PassageMetadata, str]]) -> None:
        """Replace stored metadata, reusing the stored vectors (the text is unchanged)."""
        if not items:
            return
        ids = [meta.chunk_id for meta, _ in items]
        stored = self._collection.get(ids=ids, include=["embeddings"])
        vectors = {cid: list(map(float, vec)) for cid, vec in zip(stored["ids"], stored["embeddings"], strict=True)}
        self._collection.upsert(
            ids=ids,
            embeddings=[vectors[cid] for cid in ids],
            documents=[text for _, text in items],
            metadatas=[to_chroma_metadata(meta, self.embedding_model_name) for meta, _ in items],
        )
        log_event(logger, 20, "passage_metadata_replaced", collection=self.collection_name, count=len(ids))

    def upsert(
        self,
        items: Sequence[tuple[PassageMetadata, str]],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        """Write passages with their vectors (caller decides what needs writing)."""
        if len(items) != len(embeddings):
            raise ValueError("items and embeddings must have the same length")
        if not items:
            return
        ids = [meta.chunk_id for meta, _ in items]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate chunk_id values inside one upsert batch")
        self._collection.upsert(
            ids=ids,
            embeddings=[list(map(float, vec)) for vec in embeddings],
            documents=[text for _, text in items],
            metadatas=[to_chroma_metadata(meta, self.embedding_model_name) for meta, _ in items],
        )
        log_event(logger, 20, "passages_upserted", collection=self.collection_name, count=len(ids))

    def get(self, chunk_ids: Sequence[str]) -> list[StoredPassage]:
        """Fetch stored passages by ID (missing IDs are simply not returned)."""
        if not chunk_ids:
            return []
        result = self._collection.get(ids=list(chunk_ids), include=["documents", "metadatas"])
        return [
            StoredPassage(chunk_id=cid, text=doc or "", metadata=from_chroma_metadata(meta or {}))
            for cid, doc, meta in zip(result["ids"], result["documents"] or [], result["metadatas"] or [], strict=True)
        ]

    def list_passages(
        self, where: dict[str, Any] | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[int, list[StoredPassage]]:
        """Page through stored passages in natural chunk_id order (p2 before p10).
        Returns (total, page)."""
        if limit < 1 or offset < 0:
            raise ValueError("limit must be >= 1 and offset >= 0")
        ids = sorted(self._collection.get(where=where or None, include=[])["ids"], key=natural_key)
        page_ids = ids[offset : offset + limit]
        by_id = {p.chunk_id: p for p in self.get(page_ids)}
        return len(ids), [by_id[i] for i in page_ids if i in by_id]

    def facets(self) -> dict[str, dict[str, int]]:
        """Counts of passages per organisation, CTD section, document type and status."""
        keys = ("issuing_organization", "ctd_section", "document_type", "applicability_status")
        out: dict[str, dict[str, int]] = {k: {} for k in keys}
        for meta in self._collection.get(include=["metadatas"])["metadatas"] or []:
            for k in keys:
                value = (meta or {}).get(k)
                if value is not None:
                    out[k][str(value)] = out[k].get(str(value), 0) + 1
        return {k: dict(sorted(v.items())) for k, v in out.items()}

    def all_metadata(self) -> list[dict[str, Any]]:
        """Raw stored metadata for every passage (no text, no vectors). Used for coverage reports."""
        return [dict(m or {}) for m in self._collection.get(include=["metadatas"])["metadatas"] or []]

    def all_ids(self) -> list[str]:
        return list(self._collection.get(include=[])["ids"])

    def delete(self, chunk_ids: Sequence[str]) -> None:
        if chunk_ids:
            self._collection.delete(ids=list(chunk_ids))

    def query(
        self,
        query_embedding: Sequence[float],
        n_results: int,
        where: dict[str, Any] | None = None,
    ) -> list[QueryHit]:
        """Nearest-neighbour search. Returns [] for an empty collection."""
        if n_results < 1:
            raise ValueError("n_results must be >= 1")
        if self.count() == 0:
            return []
        result = self._collection.query(
            query_embeddings=[list(map(float, query_embedding))],
            n_results=n_results,
            where=where or None,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[QueryHit] = []
        for cid, doc, meta, dist in zip(
            result["ids"][0],
            (result["documents"] or [[]])[0],
            (result["metadatas"] or [[]])[0],
            (result["distances"] or [[]])[0],
            strict=True,
        ):
            hits.append(
                QueryHit(
                    chunk_id=cid,
                    text=doc or "",
                    metadata=from_chroma_metadata(meta or {}),
                    distance=float(dist),
                )
            )
        return hits
