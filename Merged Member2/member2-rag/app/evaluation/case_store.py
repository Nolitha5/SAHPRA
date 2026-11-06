"""Read and edit the benchmark question file (benchmarks/benchmark.jsonl).

The JSONL file stays the single source of truth, so the dashboard and
`scripts/evaluate_retrieval.py` always use the same questions. Writes are
atomic (write to a temp file, then replace) so a crash never leaves a
half-written benchmark.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from app.evaluation.benchmark import BenchmarkItem, load_benchmark

_LOCK = threading.Lock()


class CaseExistsError(ValueError):
    pass


class CaseNotFoundError(KeyError):
    pass


class BenchmarkCaseStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def list(self) -> list[BenchmarkItem]:
        if not self.path.exists() or not self.path.read_text(encoding="utf-8-sig").strip():
            return []
        return load_benchmark(self.path)

    def add(self, item: BenchmarkItem) -> BenchmarkItem:
        with _LOCK:
            items = self.list()
            if any(i.question_id == item.question_id for i in items):
                raise CaseExistsError(f"question_id '{item.question_id}' already exists")
            items.append(item)
            self._write(items)
        return item

    def delete(self, question_id: str) -> None:
        with _LOCK:
            items = self.list()
            kept = [i for i in items if i.question_id != question_id]
            if len(kept) == len(items):
                raise CaseNotFoundError(question_id)
            self._write(kept)

    def _write(self, items: list[BenchmarkItem]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".benchmark-", suffix=".jsonl")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for item in items:
                    handle.write(json.dumps(item.model_dump(mode="json", exclude_none=True)) + "\n")
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
