"""BGE embedding models behind a small, replaceable interface.

Key points (from the BAAI/bge-*-en-v1.5 model cards):
* Passages are embedded as-is.
* Queries get the instruction prefix
  "Represent this sentence for searching relevant passages: " which improves
  short-query -> long-passage retrieval.
* Embeddings are L2-normalised, so cosine similarity == dot product.

The model is loaded lazily and cached per (model name, device), so it is loaded
once per process and reused by indexing, retrieval and every agent.

Any object that satisfies the `EmbeddingModel` protocol can replace BGE (this
is how the benchmark compares bge-large vs bge-small, and how unit tests use a
tiny fake model without downloading anything).
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

import numpy as np

from app.logging_utils import get_logger, log_event

logger = get_logger("embeddings")

_MODEL_CACHE: dict[tuple[str, str], Any] = {}
_CACHE_LOCK = threading.Lock()


@runtime_checkable
class EmbeddingModel(Protocol):
    """Interface every embedding backend must implement."""

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _load_sentence_transformer(model_name: str, device: str) -> Any:
    """Load (or fetch from cache) a SentenceTransformer model."""
    key = (model_name, device)
    with _CACHE_LOCK:
        if key not in _MODEL_CACHE:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise ImportError(
                    "sentence-transformers is not installed. Run: pip install -r requirements.txt"
                ) from exc
            log_event(logger, 20, "loading_embedding_model", model=model_name, device=device)
            _MODEL_CACHE[key] = SentenceTransformer(model_name, device=device)
        return _MODEL_CACHE[key]


class BGEEmbeddings:
    """Sentence-Transformers wrapper for BGE embedding models."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-en-v1.5",
        query_instruction: str = "Represent this sentence for searching relevant passages: ",
        device: str = "cpu",
        batch_size: int = 16,
    ) -> None:
        self._model_name = model_name
        self.query_instruction = query_instruction
        self.device = device
        self.batch_size = batch_size
        self._model: Any | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = _load_sentence_transformer(self._model_name, self.device)
        return self._model

    @property
    def dimension(self) -> int:

        getter = getattr(self.model, "get_embedding_dimension", None) or self.model.get_sentence_embedding_dimension
        return int(getter())

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32).tolist()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed stored passages (no instruction prefix)."""
        if not texts:
            return []
        return self._encode(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query (with the BGE query instruction)."""
        return self._encode([f"{self.query_instruction}{text}"])[0]


def build_embedder(settings: Any) -> BGEEmbeddings:
    """Create the embedder described by `Settings`."""
    return BGEEmbeddings(
        model_name=settings.embedding_model,
        query_instruction=settings.embedding_query_instruction,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
    )
