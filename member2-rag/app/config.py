"""Environment-based configuration for Member 2 (Retrieval & Knowledge Base).

Every setting has a sensible default and can be overridden with an environment
variable (or a `.env` file in the project root). Nothing here is a secret, but
the `.env` file is still git-ignored so local paths never leak into the repo.

Usage:
    from app.config import get_settings
    settings = get_settings()
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

try:  # python-dotenv is optional at runtime; tests do not need it.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore[assignment]

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Official BGE v1.5 English query instruction (see the BAAI/bge-*-en-v1.5 model
# cards). It is prepended to *queries only*, never to stored passages.
BGE_EN_V15_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"Environment variable {name} must be >= {minimum}, got {value}")
    return value


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    lowered = raw.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Environment variable {name} must be true/false, got {raw!r}")


@dataclass(frozen=True)
class Settings:
    """All tunable parameters for the knowledge base, retrieval and agents."""

    # --- Storage -----------------------------------------------------------
    chroma_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "chroma")
    collection_name: str = "kb_v2_large_w300"

    # --- Embeddings --------------------------------------------------------
    embedding_model: str = "BAAI/bge-large-en-v1.5"
    embedding_query_instruction: str = BGE_EN_V15_QUERY_INSTRUCTION
    embedding_device: str = "cpu"  # "cpu", "cuda" or "mps"
    embedding_batch_size: int = 16

    # --- Reranking ---------------------------------------------------------
    reranker_enabled: bool = True
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_max_length: int = 512
    reranker_batch_size: int = 16

    # --- Retrieval ---------------------------------------------------------
    candidate_k: int = 20  # passages fetched from ChromaDB before reranking
    final_k: int = 5  # passages returned after reranking
    max_query_chars: int = 2000

    # --- Evidence sufficiency heuristics -----------------------------------
    # These are NOT probabilities and NOT proof of regulatory correctness.
    # They decide only whether a passage is strong enough to be *shown to an
    # assessor as candidate evidence*. Calibrate them on the benchmark.
    min_rerank_score: float = 0.0  # raw cross-encoder logit
    min_retrieval_score: float = 0.55  # cosine similarity (normalised vectors)

    # --- Logging -----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True

    # --- Web API / dashboard ----------------------------------------------
    api_host: str = "127.0.0.1"  # localhost only by default
    api_port: int = 8000
    # Editing (import/delete passages, edit benchmark cases) is DISABLED unless
    # a token is set. The dashboard sends it in the X-Admin-Token header.
    admin_token: str = field(default="", repr=False)
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    benchmark_file: Path = field(default_factory=lambda: PROJECT_ROOT / "benchmarks" / "benchmark.jsonl")
    results_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "results")
    web_dist: Path = field(default_factory=lambda: PROJECT_ROOT.parent / "dist")
    max_upload_mb: int = 20
    # The list of sources the knowledge base is expected to contain (Coverage tab).
    sources_manifest: Path = field(default_factory=lambda: PROJECT_ROOT / "sources" / "kb_v2_manifest.json")
    # Tables found in the source PDFs (written by scripts/pdf_to_jsonl.py next to the passages).
    tables_file: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "processed" / "kb_v2_w300_tables.json")

    def with_overrides(self, **changes: object) -> Settings:
        """Return a copy with some fields changed (handy for tests/benchmarks)."""
        return replace(self, **changes)  # type: ignore[arg-type]

    def validate(self) -> Settings:
        if self.final_k > self.candidate_k:
            raise ValueError(
                f"final_k ({self.final_k}) cannot be larger than candidate_k ({self.candidate_k})"
            )
        if not self.collection_name.strip():
            raise ValueError("collection_name must not be empty")
        if self.admin_token and len(self.admin_token) < 12:
            raise ValueError("M2_ADMIN_TOKEN must be at least 12 characters (or empty to disable editing)")
        return self


def load_settings(env_file: Path | None = None) -> Settings:
    """Build Settings from environment variables (and `.env` if present)."""
    if load_dotenv is not None:
        load_dotenv(env_file or PROJECT_ROOT / ".env", override=False)

    chroma_dir_raw = _env_str("M2_CHROMA_DIR", str(PROJECT_ROOT / "data" / "chroma"))
    chroma_dir = Path(chroma_dir_raw)
    if not chroma_dir.is_absolute():
        chroma_dir = PROJECT_ROOT / chroma_dir

    settings = Settings(
        chroma_dir=chroma_dir,
        collection_name=_env_str("M2_COLLECTION_NAME", "kb_v2_large_w300"),
        embedding_model=_env_str("M2_EMBEDDING_MODEL", "BAAI/bge-large-en-v1.5"),
        embedding_query_instruction=os.getenv(
            "M2_EMBEDDING_QUERY_INSTRUCTION", BGE_EN_V15_QUERY_INSTRUCTION
        ),
        embedding_device=_env_str("M2_DEVICE", "cpu"),
        embedding_batch_size=_env_int("M2_EMBEDDING_BATCH_SIZE", 16),
        reranker_enabled=_env_bool("M2_RERANKER_ENABLED", True),
        reranker_model=_env_str("M2_RERANKER_MODEL", "BAAI/bge-reranker-base"),
        reranker_max_length=_env_int("M2_RERANKER_MAX_LENGTH", 512),
        reranker_batch_size=_env_int("M2_RERANKER_BATCH_SIZE", 16),
        candidate_k=_env_int("M2_CANDIDATE_K", 20),
        final_k=_env_int("M2_FINAL_K", 5),
        max_query_chars=_env_int("M2_MAX_QUERY_CHARS", 2000),
        min_rerank_score=_env_float("M2_MIN_RERANK_SCORE", 0.0),
        min_retrieval_score=_env_float("M2_MIN_RETRIEVAL_SCORE", 0.55),
        log_level=_env_str("M2_LOG_LEVEL", "INFO").upper(),
        log_json=_env_bool("M2_LOG_JSON", True),
        api_host=_env_str("M2_API_HOST", "127.0.0.1"),
        api_port=_env_int("M2_API_PORT", 8000),
        admin_token=os.getenv("M2_ADMIN_TOKEN", "").strip(),
        cors_origins=tuple(
            o.strip()
            for o in _env_str("M2_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
            if o.strip()
        ),
        benchmark_file=_path("M2_BENCHMARK_FILE", PROJECT_ROOT / "benchmarks" / "benchmark.jsonl"),
        results_dir=_path("M2_RESULTS_DIR", PROJECT_ROOT / "results"),
        web_dist=_path("M2_WEB_DIST", PROJECT_ROOT.parent / "dist"),
        max_upload_mb=_env_int("M2_MAX_UPLOAD_MB", 20),
        sources_manifest=_path("M2_SOURCES_MANIFEST", PROJECT_ROOT / "sources" / "kb_v2_manifest.json"),
        tables_file=_path("M2_TABLES_FILE", PROJECT_ROOT / "data" / "processed" / "kb_v2_w300_tables.json"),
    )
    return settings.validate()


def _path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    p = Path(raw)
    return p if p.is_absolute() else PROJECT_ROOT / p


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings for the running process."""
    return load_settings()
