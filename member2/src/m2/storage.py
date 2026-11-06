"""Vector storage adapters. Chroma embeds explicitly: prevents model/index mismatch."""
import json
import re
import hashlib
from pathlib import Path
from typing import Protocol
import numpy as np
from .schemas import RegulatoryChunk
from .embeddings import Embedder

class VectorStore(Protocol):
    def upsert(self, chunks: list[RegulatoryChunk]): ...
    def search(self, query: str, limit: int) -> list[tuple[RegulatoryChunk, float]]: ...
    def all_chunks(self) -> list[RegulatoryChunk]: ...
    def count(self) -> int: ...

class MemoryVectorStore:
    def __init__(self, embedder: Embedder):
        self.embedder = embedder
        self._chunks: dict[str, RegulatoryChunk] = {}
        self._vectors: dict[str, list[float]] = {}

    def upsert(self, chunks: list[RegulatoryChunk]):
        if not chunks: return
        embeddings = self.embedder.embed([c.text for c in chunks])
        for chunk, vec in zip(chunks, embeddings):
            self._chunks[chunk.chunk_id] = chunk
            self._vectors[chunk.chunk_id] = vec

    def search(self, query: str, limit: int) -> list[tuple[RegulatoryChunk, float]]:
        q = np.asarray(self.embedder.embed([query], query=True)[0], dtype=float)
        arr = []
        for cid, doc in self._chunks.items():
            v = np.asarray(self._vectors[cid], dtype=float)
            similarity = float(np.dot(q, v) / max(np.linalg.norm(q) * np.linalg.norm(v), 1e-12))
            arr.append((doc, max(0.0, similarity)))
        return sorted(arr, key=lambda d: (-d[1], d[0].chunk_id))[:limit]

    def all_chunks(self): return list(self._chunks.values())
    def count(self): return len(self._chunks)

class ChromaVectorStore:
    def __init__(self, embedder: Embedder, path: str, collection_prefix: str = "regulatory"):
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError('Install ChromaDB: pip install -e ".[vector]"') from exc
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=str(path))
        digest = hashlib.sha256(f"{embedder.name}:{embedder.dimension}".encode()).hexdigest()[:12]
        self.collection_name = f"{collection_prefix}-{digest}"
        self.collection = self.client.get_or_create_collection(self.collection_name, metadata={"hnsw:space": "cosine"})

    def upsert(self, chunks: list[RegulatoryChunk]):
        if not chunks: return
        for start in range(0, len(chunks), 100):
            subset = chunks[start:start+100]
            vectors = self.embedder.embed([c.text for c in subset])
            self.collection.upsert(ids=[c.chunk_id for c in subset], embeddings=vectors,
                documents=[c.text for c in subset],
                metadatas=[{"source_id": c.source_id, "section": c.section,
                            "serialized_chunk": c.model_dump_json()} for c in subset])

    def search(self, query: str, limit: int) -> list[tuple[RegulatoryChunk, float]]:
        if self.count() == 0: return []
        q = self.embedder.embed([query], query=True)[0]
        res = self.collection.query(query_embeddings=[q], n_results=min(limit, self.count()),
                                    include=["metadatas", "distances"])
        return [(RegulatoryChunk.model_validate_json(m["serialized_chunk"]),
                 max(0.0, min(1.0, 1.0-float(dist))))
                for m, dist in zip(res["metadatas"][0], res["distances"][0])]

    def all_chunks(self) -> list[RegulatoryChunk]:
        chunks = []
        for offset in range(0, self.count(), 500):
            response = self.collection.get(offset=offset, limit=500, include=["metadatas"])
            chunks.extend(RegulatoryChunk.model_validate_json(m["serialized_chunk"]) for m in response["metadatas"])
        return chunks

    def count(self): return self.collection.count()
