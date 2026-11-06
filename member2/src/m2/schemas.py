"""Provisional interoperable contracts. M1 must ratify shared Finding fields."""
from __future__ import annotations
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

class SourceType(str, Enum):
    REGULATORY = "regulatory"
    SPONSOR = "sponsor"
    SYNTHETIC = "synthetic"
    LITERATURE = "literature"

class SourceRecord(StrictModel):
    source_id: str = Field(min_length=1)
    authority: str = Field(min_length=1)
    title: str = Field(min_length=1)
    document_code: str = Field(min_length=1)
    version: str = Field(min_length=1)
    publication_date: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    url: str | None = None
    license_note: str | None = None
    source_type: SourceType = SourceType.REGULATORY
    approved: bool = False
    sha256: str | None = None
    provenance_verified: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def check_date_interval(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to precedes effective_from")
        return self

class RegulatoryChunk(StrictModel):
    chunk_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    section: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    chunk_kind: str = "text"
    checksum: str | None = None
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)

class DossierChunk(StrictModel):
    chunk_id: str
    document_id: str
    ctd_section: str
    text: str
    page: int | None = Field(default=None, ge=1)
    kind: str = "text"
    table_rows: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    quality_flag: str | None = None

class EvidenceFilters(StrictModel):
    authorities: list[str] = Field(default_factory=list)
    document_codes: list[str] = Field(default_factory=list)
    sections: list[str] = Field(default_factory=list)
    effective_on: date | None = None
    include_literature: bool = False

class EvidenceRequest(StrictModel):
    request_id: str
    question: str = Field(min_length=3)
    requesting_agent: str
    case_id: str | None = None
    filters: EvidenceFilters = Field(default_factory=EvidenceFilters)
    top_k: int = Field(default=5, ge=1, le=100)

class EvidenceStatus(str, Enum):
    FOUND = "FOUND"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    ERROR = "ERROR"

class EvidencePassage(StrictModel):
    evidence_id: str
    chunk_id: str
    source_id: str
    authority: str
    document: str
    document_code: str
    section: str
    version: str
    passage: str
    page: int | None = None
    source_url: str | None = None
    source_sha256: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    retrieval_score: float = Field(ge=0.0, le=1.0)
    citation: str
    provenance_verified: bool
    is_synthetic: bool = False
    source_type: SourceType = SourceType.REGULATORY

class EvidenceResult(StrictModel):
    request_id: str
    status: EvidenceStatus
    evidence: list[EvidencePassage] = Field(default_factory=list)
    requires_human_review: bool = False
    reason: str | None = None
    index_id: str | None = None
    retrieval_config: dict[str, Any] = Field(default_factory=dict)
    @model_validator(mode="after")
    def valid_status(self):
        if self.status != EvidenceStatus.FOUND and self.evidence:
            raise ValueError("Non-FOUND result must have no evidence")
        if self.status == EvidenceStatus.FOUND and not self.evidence:
            raise ValueError("FOUND result must include evidence")
        if self.status != EvidenceStatus.FOUND and not self.requires_human_review:
            raise ValueError("Retrieval failure/insufficiency requires human review")
        return self

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
    page: int | None = None

class Finding(StrictModel):
    finding_id: str
    case_id: str
    agent_id: str
    ctd_section: str
    issue_type: str
    status: FindingStatus
    sponsor_evidence: list[SponsorEvidence] = Field(default_factory=list)
    regulatory_evidence: list[EvidencePassage] = Field(default_factory=list)
    rationale: str
    uncertainty: float = Field(ge=0.0, le=1.0)
    qa_status: QAStatus = QAStatus.PENDING
    requires_human_review: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attributes: dict[str, Any] = Field(default_factory=dict)

class S4ReviewRequest(StrictModel):
    case_id: str
    dossier_chunks: list[DossierChunk]
    as_of: date | None = None
    relevant_regulatory_codes: list[str] = Field(default_factory=list)

class S4ReviewResult(StrictModel):
    case_id: str
    agent_id: Literal["S4_CONTROL"] = "S4_CONTROL"
    findings: list[Finding]
    status: str = "REVIEW_REQUIRED"

class GoldQuery(StrictModel):
    query_id: str
    question: str
    relevant_chunk_ids: list[str]
    filters: EvidenceFilters = Field(default_factory=EvidenceFilters)

class BenchmarkReport(StrictModel):
    config: dict[str, Any]
    evaluated_queries: int
    aggregate: dict[str, float]
    per_query: list[dict[str, Any]]
    caution: str = "Scores require expert-reviewed gold labels and approved real regulatory documents."
