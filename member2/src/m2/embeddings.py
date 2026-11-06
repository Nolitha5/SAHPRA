"""Embedders. HashEmbedder is strictly a zero-download DEMO baseline."""
import hashlib
import re
from typing import Protocol
import numpy as np

class Embedder(Protocol):
    name: str
    dimension: int
    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]: ...

class HashEmbedder:
    def __init__(self, dimension: int = 384):
        self.name = "hash-demo-v1"
        self.dimension = dimension

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        data = []
        for text in texts:
            vector = np.zeros(self.dimension, dtype=np.float32)
            for token in re.findall(r"[\w]+", text.casefold()):
                digest = hashlib.blake2s(token.encode("utf-8"), digest_size=8).digest()
                idx = int.from_bytes(digest[:4], "big") % self.dimension
                vector[idx] += 1.0
            norm = np.linalg.norm(vector)
            if norm:
                vector /= norm
            data.append(vector.tolist())
        return data

class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, *, local_files_only: bool = False):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError('Install model extra: pip install -e ".[models]"') from exc
        self.name = model_name
        # For controlled offline use pre-download the model and pass local_files_only=True.
        self._model = SentenceTransformer(model_name, local_files_only=local_files_only, trust_remote_code=False)
        self.dimension = self._model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        if not texts: return []
        # bge-large-en-v1.5 convention; do not prepend to documents.
        if query and self.name.casefold().endswith("bge-large-en-v1.5"):
            texts = ["Represent this sentence for searching relevant passages: " + t for t in texts]
        vectors = self._model.encode(texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
        return vectors.tolist()


def build_embedder(model: str, dimension: int = 384, *, offline: bool = False) -> Embedder:
    if model == "hash-demo-v1":
        return HashEmbedder(dimension)
    return SentenceTransformerEmbedder(model, local_files_only=offline)
