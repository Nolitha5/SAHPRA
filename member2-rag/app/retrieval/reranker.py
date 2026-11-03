"""BGE cross-encoder reranking.

A cross-encoder reads the query and a passage *together* and outputs one
relevance score. It is slower than embedding search but much more precise, so
we use it only on the small candidate set returned by ChromaDB.

Scores are RAW LOGITS (we set the activation to Identity explicitly, because
sentence-transformers would otherwise apply a sigmoid by default). A higher
score means "more relevant to the query" - nothing more. It is not a
probability, and it says nothing about whether a dossier complies.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from app.logging_utils import get_logger, log_event
from app.schemas import RetrievedPassage

logger = get_logger("reranker")

_MODEL_CACHE: dict[tuple[str, str, int], Any] = {}
_CACHE_LOCK = threading.Lock()


@runtime_checkable
class Reranker(Protocol):
    model_name: str

    def score(self, query: str, passages: Sequence[str]) -> list[float]: ...


class BGEReranker:
    """sentence-transformers CrossEncoder wrapper for BAAI/bge-reranker-*."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-base",
        device: str = "cpu",
        max_length: int = 512,
        batch_size: int = 16,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self.max_length = max_length
        self.batch_size = batch_size
        self._model: Any | None = None

    @property
    def model(self) -> Any:
        if self._model is None:
            key = (self.model_name, self.device, self.max_length)
            with _CACHE_LOCK:
                if key not in _MODEL_CACHE:
                    try:
                        import torch
                        from sentence_transformers import CrossEncoder
                    except ImportError as exc:  # pragma: no cover
                        raise ImportError(
                            "sentence-transformers is not installed. Run: pip install -r requirements.txt"
                        ) from exc
                    log_event(logger, 20, "loading_reranker", model=self.model_name, device=self.device)
                    _MODEL_CACHE[key] = CrossEncoder(
                        self.model_name,
                        device=self.device,
                        max_length=self.max_length,
                        activation_fn=torch.nn.Identity(),
                    )
                self._model = _MODEL_CACHE[key]
        return self._model

    def score(self, query: str, passages: Sequence[str]) -> list[float]:
        if not passages:
            return []
        pairs = [(query, passage) for passage in passages]
        scores = self.model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
        return [float(s) for s in scores]


def rerank(
    reranker: Reranker,
    query: str,
    passages: Sequence[RetrievedPassage],
    top_n: int,
) -> list[RetrievedPassage]:
    """Score, sort (descending) and truncate passages.

    The original `retrieval_score` / `retrieval_rank` are kept unchanged; the
    reranker's output is stored separately in `rerank_score` / `rerank_rank`.
    Ties keep the original retrieval order (Python's sort is stable).
    """
    if top_n < 1:
        raise ValueError("top_n must be >= 1")
    if not passages:
        return []
    scores = reranker.score(query, [p.text for p in passages])
    if len(scores) != len(passages):
        raise RuntimeError("reranker returned a different number of scores than passages")
    scored = sorted(zip(passages, scores, strict=True), key=lambda pair: pair[1], reverse=True)[:top_n]
    return [
        passage.model_copy(update={"rerank_score": round(score, 6), "rerank_rank": rank})
        for rank, (passage, score) in enumerate(scored, start=1)
    ]


def build_reranker(settings: Any) -> BGEReranker | None:
    if not settings.reranker_enabled:
        return None
    return BGEReranker(
        model_name=settings.reranker_model,
        device=settings.embedding_device,
        max_length=settings.reranker_max_length,
        batch_size=settings.reranker_batch_size,
    )
