"""Load processed passages (JSONL from Member 3), validate and index them.

Validation behaviour:
* Each line is parsed and validated independently; one bad line does not stop
  the rest from loading, but every rejection is reported with its line number
  and the failing field names (never the passage text).
* Two lines with the same chunk_id but different text are a conflict: both are
  rejected so the wrong version is never indexed by accident.
* Two lines with the same chunk_id and identical text: the second is skipped.
* Use `strict=True` to abort if any line is invalid.

Indexing behaviour:
* Unchanged passages (same ID and hash already in the store) are not
  re-embedded, which makes re-running the loader cheap and idempotent.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from app.embeddings.bge_embeddings import EmbeddingModel
from app.knowledge_base.document_store import ChromaDocumentStore
from app.logging_utils import get_logger, log_event
from app.schemas import PassageMetadata, PassageRecord

logger = get_logger("indexing")


class InputFileError(ValueError):
    """The input file cannot be used at all (missing, empty, wrong format)."""


@dataclass
class RecordError:
    line_number: int
    chunk_id: str | None
    message: str


@dataclass
class LoadResult:
    records: list[PassageRecord] = field(default_factory=list)
    errors: list[RecordError] = field(default_factory=list)
    skipped_duplicates: list[str] = field(default_factory=list)
    lines_read: int = 0


@dataclass
class IndexReport:
    source_file: str | None
    lines_read: int
    valid_records: int
    rejected: list[RecordError]
    skipped_duplicates: int
    added: int
    updated: int
    unchanged: int
    total_in_collection: int

    def as_dict(self) -> dict:
        return {
            "source_file": self.source_file,
            "lines_read": self.lines_read,
            "valid_records": self.valid_records,
            "rejected": len(self.rejected),
            "rejected_details": [e.__dict__ for e in self.rejected],
            "skipped_duplicates": self.skipped_duplicates,
            "added": self.added,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "total_in_collection": self.total_in_collection,
        }


def _describe_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", ())) or "record"
        parts.append(f"{loc}: {err.get('msg')}")
    return "; ".join(parts)


def parse_records(lines: Iterable[str]) -> LoadResult:
    """Validate JSONL lines into `PassageRecord`s (blank lines are ignored)."""
    result = LoadResult()
    by_id: dict[str, tuple[int, PassageRecord]] = {}
    conflicted: set[str] = set()

    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        result.lines_read += 1
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError as exc:
            result.errors.append(RecordError(line_number, None, f"invalid JSON: {exc.msg}"))
            continue
        if not isinstance(obj, dict):
            result.errors.append(RecordError(line_number, None, "each line must be a JSON object"))
            continue
        try:
            record = PassageRecord(**obj)
            record.to_metadata()  # full metadata validation (CTD format, dates, ...)
        except ValidationError as exc:
            cid = obj.get("chunk_id") if isinstance(obj.get("chunk_id"), str) else None
            result.errors.append(RecordError(line_number, cid, _describe_validation_error(exc)))
            continue
        except TypeError as exc:
            result.errors.append(RecordError(line_number, None, f"invalid record: {exc}"))
            continue

        cid = record.chunk_id or ""
        if cid in conflicted:
            result.errors.append(
                RecordError(line_number, cid, "conflicting duplicate chunk_id (different text)")
            )
            continue
        if cid in by_id:
            first_line, first = by_id[cid]
            if first.content_hash == record.content_hash:
                result.skipped_duplicates.append(cid)
            else:
                conflicted.add(cid)
                del by_id[cid]
                for ln in (first_line, line_number):
                    result.errors.append(
                        RecordError(ln, cid, "conflicting duplicate chunk_id (different text)")
                    )
            continue
        by_id[cid] = (line_number, record)

    result.records = [rec for _, rec in sorted(by_id.values(), key=lambda x: x[0])]
    return result


def load_jsonl(path: Path | str) -> LoadResult:
    """Read and validate a JSONL file of processed passages."""
    path = Path(path)
    if not path.exists():
        raise InputFileError(f"Input file not found: {path}")
    if path.suffix.lower() not in {".jsonl", ".ndjson"}:
        raise InputFileError(f"Expected a .jsonl file, got: {path.name}")
    with path.open("r", encoding="utf-8-sig") as handle:  # tolerate Windows BOM
        result = parse_records(handle)
    if result.lines_read == 0:
        raise InputFileError(f"Input file is empty: {path}")
    return result


def index_records(
    records: Sequence[PassageRecord],
    store: ChromaDocumentStore,
    embedder: EmbeddingModel,
    batch_size: int = 64,
) -> tuple[int, int, int]:
    """Embed and upsert records. Returns (added, updated, unchanged)."""
    items: list[tuple[PassageMetadata, str]] = [(r.to_metadata(), r.text) for r in records]
    added = updated = unchanged = 0
    for start in range(0, len(items), batch_size):
        batch = items[start : start + batch_size]
        plan = store.plan_upsert(batch)
        to_write_ids = set(plan.added) | set(plan.updated)
        to_write = [item for item in batch if item[0].chunk_id in to_write_ids]
        if to_write:
            vectors = embedder.embed_documents([text for _, text in to_write])
            store.upsert(to_write, vectors)
        added += len(plan.added)
        updated += len(plan.updated)
        unchanged += len(plan.unchanged)
    return added, updated, unchanged


def index_jsonl(
    path: Path | str,
    store: ChromaDocumentStore,
    embedder: EmbeddingModel,
    strict: bool = False,
    dry_run: bool = False,
    batch_size: int = 64,
) -> IndexReport:
    """Validate a JSONL file and index all valid passages."""
    return index_loaded(load_jsonl(path), store, embedder, str(path), strict, dry_run, batch_size)


def index_text(
    content: str,
    store: ChromaDocumentStore,
    embedder: EmbeddingModel,
    source_name: str = "upload",
    strict: bool = False,
    dry_run: bool = False,
    batch_size: int = 64,
) -> IndexReport:
    """Validate and index JSONL supplied as a string (used by the web API upload)."""
    loaded = parse_records(content.lstrip("﻿").splitlines())
    if loaded.lines_read == 0:
        raise InputFileError("The uploaded file is empty")
    return index_loaded(loaded, store, embedder, source_name, strict, dry_run, batch_size)


def index_loaded(
    loaded: LoadResult,
    store: ChromaDocumentStore,
    embedder: EmbeddingModel,
    source_name: str,
    strict: bool = False,
    dry_run: bool = False,
    batch_size: int = 64,
) -> IndexReport:
    """Index an already-validated LoadResult."""
    path = source_name
    if strict and loaded.errors:
        raise InputFileError(
            f"{len(loaded.errors)} invalid record(s) in {path}; nothing indexed (strict mode). "
            f"First error: line {loaded.errors[0].line_number}: {loaded.errors[0].message}"
        )
    added = updated = unchanged = 0
    if not dry_run and loaded.records:
        added, updated, unchanged = index_records(loaded.records, store, embedder, batch_size)
    report = IndexReport(
        source_file=str(path),
        lines_read=loaded.lines_read,
        valid_records=len(loaded.records),
        rejected=loaded.errors,
        skipped_duplicates=len(loaded.skipped_duplicates),
        added=added,
        updated=updated,
        unchanged=unchanged,
        total_in_collection=store.count(),
    )
    log_event(
        logger,
        20,
        "index_jsonl_complete",
        source_file=Path(path).name,
        valid=report.valid_records,
        rejected=len(report.rejected),
        added=added,
        updated=updated,
        unchanged=unchanged,
        dry_run=dry_run,
    )
    return report
