"""Regulatory source registry. Regulatory status is explicit; no implicit approvals."""
import hashlib
import json
from pathlib import Path
from .schemas import SourceRecord, SourceType, EvidenceFilters

class SourceRegistry:
    def __init__(self, records: list[SourceRecord] | None = None):
        self.records: dict[str, SourceRecord] = {r.source_id: r for r in (records or [])}

    def register(self, source: SourceRecord):
        previous = self.records.get(source.source_id)
        if previous and previous.model_dump() != source.model_dump():
            raise ValueError(f"Source {source.source_id} exists with different metadata; use versioned source ID")
        self.records[source.source_id] = source

    def get(self, source_id: str) -> SourceRecord:
        return self.records[source_id]

    def eligible(self, source: SourceRecord, filters: EvidenceFilters, allow_synthetic: bool) -> bool:
        if not source.approved or not source.provenance_verified:
            return False
        if source.source_type == SourceType.SPONSOR:
            return False
        if source.source_type == SourceType.LITERATURE and not filters.include_literature:
            return False
        if source.source_type == SourceType.SYNTHETIC and not allow_synthetic:
            return False
        if filters.authorities and source.authority.casefold() not in {a.casefold() for a in filters.authorities}:
            return False
        if filters.document_codes and source.document_code.casefold() not in {a.casefold() for a in filters.document_codes}:
            return False
        if filters.effective_on:
            if source.effective_from is None:  # Unknown applicability is not considered proven
                return False
            if filters.effective_on < source.effective_from:
                return False
            if source.effective_to and filters.effective_on > source.effective_to:
                return False
        return True

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps([s.model_dump(mode="json") for s in self.records.values()], indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "SourceRegistry":
        if not Path(path).exists():
            return cls()
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([SourceRecord.model_validate(d) for d in obj])

def file_sha256(path: str | Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for buf in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(buf)
    return hasher.hexdigest()
