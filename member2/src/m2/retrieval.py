"""Evidence/RERA: one shared retrieval service; never generates a regulatory requirement."""
from __future__ import annotations
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol
from .schemas import (EvidenceRequest, EvidenceResult, EvidenceStatus, EvidencePassage,
                      RegulatoryChunk, SourceType)
from .registry import SourceRegistry
from .storage import VectorStore

TOKEN = re.compile(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*")
STOP = {"the", "a", "an", "in", "for", "of", "and", "to", "as", "with", "what", "which", "does", "is", "are", "be", "or", "on", "at", "how", "should", "under", "about", "this", "that", "do", "must"}

def tokenize(s: str) -> list[str]:
    return [w for w in TOKEN.findall(s.casefold()) if w not in STOP and len(w) > 1]

class Reranker(Protocol):
    def rank(self, query: str, passages: list[str]) -> list[float]: ...

class CrossEncoderReranker:
    def __init__(self, model_name="BAAI/bge-reranker-large", *, local_files_only=False):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as e:
            raise RuntimeError('Install model extra: pip install -e ".[models]"') from e
        self.name = model_name
        self.model = CrossEncoder(model_name, local_files_only=local_files_only, trust_remote_code=False)
    def rank(self, query: str, passages: list[str]) -> list[float]:
        if not passages: return []
        scores = self.model.predict([(query, passage) for passage in passages])
        return [float(s) for s in scores]


def lexical_bm25(query: str, chunks: list[RegulatoryChunk]) -> dict[str, float]:
    if not chunks: return {}
    tok = [tokenize(c.text) for c in chunks]
    docfreq = Counter(t for words in tok for t in set(words))
    avglen = sum(len(a) for a in tok)/len(tok) or 1.0
    n = len(tok)
    results = {}
    for chunk, words in zip(chunks, tok):
        tf = Counter(words)
        score = 0.0
        for term in set(tokenize(query)):
            if term not in tf: continue
            idf = math.log(1 + (n - docfreq[term] + 0.5)/(docfreq[term] + 0.5))
            score += idf * tf[term] * 2.2 / (tf[term] + 1.2 * (0.25 + 0.75 * len(words)/avglen))
        results[chunk.chunk_id] = score
    return results

@dataclass
class RetrievalConfig:
    min_query_token_overlap: float = 0.20
    candidate_multiplier: int = 5
    hybrid_weight: float = 0.5
    allow_synthetic: bool = False
    index_id: str = "unversioned"

class EvidenceService:
    def __init__(self, store: VectorStore, registry: SourceRegistry, *, config: RetrievalConfig | None = None,
                 reranker: Reranker | None = None):
        self.store, self.registry = store, registry
        self.config = config or RetrievalConfig()
        self.reranker = reranker

    def retrieve(self, request: EvidenceRequest) -> EvidenceResult:
        """Returns verifiable evidence or an explicit human-review status. Does not use LLM recall."""
        cfg = self.config
        try:
            all_chunks = self.store.all_chunks()
            eligible = {}
            for c in all_chunks:
                source = self.registry.records.get(c.source_id)
                if not source or not self.registry.eligible(source, request.filters, cfg.allow_synthetic):
                    continue
                if request.filters.sections and c.section.casefold() not in {s.casefold() for s in request.filters.sections}:
                    continue
                eligible[c.chunk_id] = c
            if not eligible:
                return self._no_evidence(request, "No approved, applicable indexed source meets the filters")

            # Filtering happens BEFORE ranking to avoid losing matching candidates due to truncation.
            limit = max(request.top_k * cfg.candidate_multiplier, request.top_k)
            dense = [(c, score) for c, score in self.store.search(request.question, len(all_chunks))
                     if c.chunk_id in eligible][:limit]
            lexical = lexical_bm25(request.question, list(eligible.values()))
            lexical_sorted = sorted(lexical, key=lambda x: (-lexical[x], x))[:limit]
            dense_rank = {doc.chunk_id: i + 1 for i, (doc, _) in enumerate(dense)}
            lexical_rank = {cid: i + 1 for i, cid in enumerate(lexical_sorted)}
            candidate_ids = set(dense_rank) | set(lexical_rank)
            fused = {}
            for cid in candidate_ids:
                fused[cid] = (cfg.hybrid_weight/(60 + dense_rank[cid]) if cid in dense_rank else 0.0) + (
                    (1-cfg.hybrid_weight)/(60 + lexical_rank[cid]) if cid in lexical_rank else 0.0)
            candidates = sorted(candidate_ids, key=lambda cid: (-fused[cid], cid))
            if self.reranker:
                rerank = self.reranker.rank(request.question, [eligible[cid].text for cid in candidates])
                if len(rerank) != len(candidates):
                    raise ValueError("Reranker returned wrong number of scores")
                candidates = [x for _, x in sorted(zip(rerank, candidates), key=lambda t: -t[0])]

            qtok = set(tokenize(request.question))
            passes = []
            for cid in candidates:
                chunk = eligible[cid]
                src = self.registry.get(chunk.source_id)
                searchable = " ".join([chunk.text, src.title, src.document_code, chunk.section])
                overlap = len(qtok & set(tokenize(searchable)))/max(len(qtok), 1)
                if overlap < cfg.min_query_token_overlap:
                    continue
                norm_score = fused[cid]/(1/60) if fused[cid] else 0.0
                score = max(0.0, min(1.0, norm_score))
                location = f"§{chunk.section}" + (f", p.{chunk.page}" if chunk.page else "")
                # The citation is a locator, not a compliance conclusion.
                citation = f"{src.authority}, {src.document_code}, {src.version}, {location}"
                if src.url: citation += f" ({src.url})"
                passes.append(EvidencePassage(
                    evidence_id=f"e-{cid}",chunk_id=cid,source_id=src.source_id, authority=src.authority,
                    document=src.title, document_code=src.document_code,section=chunk.section,version=src.version,
                    passage=chunk.text,page=chunk.page,source_url=src.url,source_sha256=src.sha256,
                    effective_from=src.effective_from,effective_to=src.effective_to,
                    retrieval_score=score,citation=citation,provenance_verified=src.provenance_verified,
                    is_synthetic=src.source_type == SourceType.SYNTHETIC,source_type=src.source_type))
                if len(passes) >= request.top_k: break
            if not passes:
                return self._no_evidence(request, "No indexed passage met the preliminary relevance check")
            return EvidenceResult(request_id=request.request_id,status=EvidenceStatus.FOUND,evidence=passes,
                index_id=cfg.index_id,retrieval_config=self._metadata())
        except Exception as exc:
            # An infrastructure error cannot be reported as 'no applicable regulations'.
            return EvidenceResult(request_id=request.request_id,status=EvidenceStatus.ERROR,
                requires_human_review=True,reason=f"retrieval error ({type(exc).__name__}): {exc}",
                index_id=cfg.index_id,retrieval_config=self._metadata())

    def _metadata(self):
        return {"min_query_token_overlap":self.config.min_query_token_overlap,
            "hybrid_weight":self.config.hybrid_weight,"candidate_multiplier":self.config.candidate_multiplier,
            "reranker":getattr(self.reranker,"name",None),"store":type(self.store).__name__}

    def _no_evidence(self, req, reason):
        return EvidenceResult(request_id=req.request_id,status=EvidenceStatus.INSUFFICIENT_EVIDENCE,
            reason=reason,requires_human_review=True,index_id=self.config.index_id,
            retrieval_config=self._metadata())
