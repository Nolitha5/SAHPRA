"""
Shared contract objects for M3 (Ingestion & Perception).

DossierChunk mirrors member2/src/m2/schemas.py::DossierChunk exactly (locked
with M2 on the aziz-and-sipho branch) so chunks can be handed to M2's S.4
review without any translation layer. Do not change field names/types here
without re-syncing with M2 — this is the seam the whole system depends on.

S5Claim mirrors Florah-M5's backend/models.py::S5Claim for the S.5
Reference Standards handoff to M5.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class DossierChunk(StrictModel):
    """One retrieval-sized, CTD-section-tagged piece of a sponsor dossier.

    This is the sole hand-off object from M3 to the rest of the system.
    M2 enforces (on their side) that only chunks whose ctd_section starts
    with their section of interest and carry no quality_flag are reviewed —
    so quality_flag must be set (not silently dropped) whenever extraction
    is uncertain, empty, or garbled.
    """

    chunk_id: str
    document_id: str
    ctd_section: str  # e.g. "3.2.S.4.1" — exact CTD code, never a guess
    text: str
    page: Optional[int] = Field(default=None, ge=1)
    kind: str = "text"  # "text" | "table" | "figure_caption"
    table_rows: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    quality_flag: Optional[str] = None  # set => excluded from downstream review


class S5Claim(StrictModel):
    """Structured S.5 sponsor claim extracted from the dossier, for M5."""

    substance_name: str
    standard: str  # e.g. "BP", "USP", "Ph.Eur.", "IP"
    edition_claimed: str  # e.g. "BP 2019"
    test_method: Optional[str] = None
    submission_date: date


# ── Shared structured-finding contract ───────────────────────────────
#
# These mirror member2/src/m2/schemas.py (aziz-and-sipho branch) field for
# field so that findings from M3's S.2/S.3 agents are interoperable with
# M2's S.4 agent and consumable by M1 (Orchestrator), M4 (memory/consistency)
# and M5 (QA/Critic) without any translation. The S.2/S.3 agents are
# siblings of M2's S4_CONTROL agent and MUST speak the same Finding object.
#
# NOTE on regulatory_evidence: M2 types this as list[EvidencePassage] (their
# own retrieval type). Until M3's agents are wired to M2's Evidence/RERA
# service, they produce findings with regulatory_evidence=[] (empty), which
# serialises identically. When retrieval is wired, the list holds the
# EvidencePassage dicts returned by M2 — so it is typed here as list[dict]
# to stay decoupled from M2's package while remaining wire-compatible.

from enum import Enum  # noqa: E402
from datetime import datetime, timezone  # noqa: E402


class QAStatus(str, Enum):
    PENDING = "PENDING"
    PASS = "PASS"
    FLAG = "FLAG"
    ESCALATE = "ESCALATE"


class FindingStatus(str, Enum):
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    POTENTIAL_GAP = "POTENTIAL_GAP"
    MISSING_INFORMATION = "MISSING_INFORMATION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class SponsorEvidence(StrictModel):
    document_id: str
    chunk_id: str
    ctd_section: str
    passage: str
    page: Optional[int] = None


class Finding(StrictModel):
    finding_id: str
    case_id: str
    agent_id: str  # e.g. "S2_MANUFACTURE", "S3_CHARACTERISATION"
    ctd_section: str
    issue_type: str
    status: FindingStatus
    sponsor_evidence: list[SponsorEvidence] = Field(default_factory=list)
    regulatory_evidence: list[dict[str, Any]] = Field(default_factory=list)
    rationale: str
    uncertainty: float = Field(ge=0.0, le=1.0)
    qa_status: QAStatus = QAStatus.PENDING  # M5's QA/Critic sets this later
    requires_human_review: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attributes: dict[str, Any] = Field(default_factory=dict)
