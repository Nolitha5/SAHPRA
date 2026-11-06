"""Composable Member-2 runtime. May be embedded by M1 without starting a second server."""
from __future__ import annotations
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Any
from .registry import SourceRegistry
from .embeddings import build_embedder
from .storage import MemoryVectorStore, ChromaVectorStore
from .sqlite_vectors import SQLiteVectorStore
from .retrieval import EvidenceService, RetrievalConfig, CrossEncoderReranker
from .s4 import S4ControlAgent
from .ollama import OllamaClient
from .schemas import RegulatoryChunk

@dataclass
class AppConfig:
    mode: str = "demo"
    backend: str = "memory"
    index_path: str = "local_indexes/chroma"
    registry_path: str = "local_indexes/sources.json"
    embedding_model: str = "hash-demo-v1"
    embedding_dimension: int = 384
    rerank_model: str | None = None
    min_query_token_overlap: float = 0.2
    hybrid_weight: float = 0.5
    candidate_multiplier: int = 5
    allow_synthetic: bool = False
    use_ollama_s4: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    offline_models: bool = False

    @classmethod
    def from_file(cls,path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(**data)

class M2Runtime:
    def __init__(self, cfg: AppConfig, registry: SourceRegistry | None = None):
        if cfg.mode not in {"demo", "research"}:
            raise ValueError("mode must be demo or research")
        if cfg.mode == "research" and (cfg.embedding_model == "hash-demo-v1" or cfg.allow_synthetic):
            raise ValueError("research mode forbids synthetic sources and demonstration embeddings")
        if cfg.backend not in {"memory","chroma","sqlite"}:
            raise ValueError("backend must be memory, chroma or sqlite")
        if cfg.mode == "research" and cfg.backend == "sqlite":
            raise ValueError("SQLite fallback is for engineering demos only; research requires ChromaDB or approved replacement")
        if not 0 <= cfg.hybrid_weight <= 1: raise ValueError("hybrid_weight must be between 0 and 1")
        self.cfg = cfg
        self.registry = registry or SourceRegistry.load(cfg.registry_path)
        self.embedder = build_embedder(cfg.embedding_model,cfg.embedding_dimension,offline=cfg.offline_models)
        self.store = (MemoryVectorStore(self.embedder) if cfg.backend == "memory" else
                      SQLiteVectorStore(self.embedder,cfg.index_path) if cfg.backend == "sqlite" else
                      ChromaVectorStore(self.embedder,cfg.index_path))
        reranker = CrossEncoderReranker(cfg.rerank_model,local_files_only=cfg.offline_models) if cfg.rerank_model else None
        rcfg = RetrievalConfig(min_query_token_overlap=cfg.min_query_token_overlap,
            candidate_multiplier=cfg.candidate_multiplier,hybrid_weight=cfg.hybrid_weight,
            allow_synthetic=cfg.allow_synthetic,
            index_id=getattr(self.store,"collection_name",cfg.embedding_model))
        self.evidence = EvidenceService(self.store,self.registry,config=rcfg,reranker=reranker)
        llm = OllamaClient(model=cfg.ollama_model,base_url=cfg.ollama_base_url) if cfg.use_ollama_s4 else None
        self.s4 = S4ControlAgent(self.evidence,llm=llm)

    def index(self,chunks: list[RegulatoryChunk]):
        for chunk in chunks:
            if chunk.source_id not in self.registry.records:
                raise ValueError(f"Unregistered source: {chunk.source_id}")
            source = self.registry.get(chunk.source_id)
            if not source.approved or not source.provenance_verified:
                raise ValueError(f"Unapproved/unverified source cannot be indexed: {chunk.source_id}")
            if self.cfg.mode == "research" and (not source.sha256 or len(source.sha256) != 64):
                raise ValueError("Research source requires a verified SHA-256 document hash")
            if source.source_type.value == "sponsor":
                raise ValueError("Sponsor material cannot be indexed in the regulatory knowledge base")
            if source.source_type.value == "synthetic" and not self.cfg.allow_synthetic:
                raise ValueError("Synthetic records disabled")
        self.store.upsert(chunks)

    def stats(self) -> dict[str,Any]:
        return {"backend":self.cfg.backend,"embedding_model":self.embedder.name,
            "source_count":len(self.registry.records),"chunk_count":self.store.count(),
            "mode":self.cfg.mode,"allow_synthetic":self.cfg.allow_synthetic}
