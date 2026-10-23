"""
Replaceable adapter for Member 4 (Memory / Evaluation).

M4 supplies:
  - An audit log endpoint or file schema for recording assessor decisions.
  - An evaluation harness that scores findings against golden-answer JSON files.

CONTRACT STILL REQUIRED FROM M4:
  - Endpoint URL (or shared file path) for writing audit records
  - Audit record schema: which fields M4 expects (finding_id, decision,
    disposition_note, timestamp, assessor identifier, dossier reference?)
  - Whether records are appended (event log) or upserted (latest state)
  - Confirmation mechanism: does M4 return an acknowledgement?
  - Location of tests/golden/ confirmed as the agreed path for golden-answer files

Until M4 supplies these contracts, LocalFileAuditAdapter writes records to a
local JSONL file.  The API endpoint explicitly reports whether the record was
saved to the stub or to M4's real service.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


@dataclass
class AuditRecord:
    finding_id: str
    decision: str
    disposition_note: str | None
    timestamp: str          # ISO-8601 UTC
    assessor_id: str = "stub-assessor"   # replace when auth is in place
    dossier_id: str = "unknown"


class M4AuditAdapter(Protocol):
    def record_decision(self, record: AuditRecord) -> bool:
        """
        Persist an assessor decision.
        Returns True if the record was successfully stored, False otherwise.
        """
        ...


class LocalFileAuditAdapter:
    """
    Stub: appends audit records as JSON lines to data/audit_log.jsonl.
    Replace with a real M4 API call once the contract is supplied.
    """

    def __init__(self, log_path: Path | None = None) -> None:
        self._path = log_path or (
            Path(__file__).parent.parent / "data" / "audit_log.jsonl"
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record_decision(self, record: AuditRecord) -> bool:
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(record)) + "\n")
            return True
        except OSError:
            return False


def make_audit_record(
    finding_id: str,
    decision: str,
    disposition_note: str | None,
) -> AuditRecord:
    return AuditRecord(
        finding_id=finding_id,
        decision=decision,
        disposition_note=disposition_note,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
    )
