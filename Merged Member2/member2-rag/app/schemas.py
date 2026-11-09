"""Shared data contracts (Pydantic v2) for Member 2.

Three groups of models live here:

1. **Input contract with Member 3** - `PassageRecord`: one processed regulatory
   passage per JSONL line.
2. **Retrieval contract** - `SearchFilters`, `RetrievedPassage`,
   `RetrievalResult`: what the shared retrieval service returns.
3. **Team finding contract with Member 1 / 5** - `Finding` and its parts:
   the single object every agent returns to the Orchestrator.

Field names use snake_case so they map one-to-one onto JSON and onto the
Orchestrator's state.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.hashing import compute_content_hash, make_chunk_id

SCHEMA_VERSION = "1.0"

_CHUNK_ID_RE = re.compile(r"^[A-Za-z0-9._:\-]{1,200}$")
# Matches CTD headings such as "3.2.S", "3.2.S.4", "3.2.S.4.1", "3.2.P.5", "2.3.S".
_CTD_RE = re.compile(r"^[1-5](\.\d+)*(\.[A-Z](\.\d+)*)?$")
# ISO date with optional month/day: "2009", "2009-06", "2009-06-15".
_PARTIAL_DATE_RE = re.compile(r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$")


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
class DocumentType(str, Enum):
    GUIDELINE = "guideline"
    GUIDANCE = "guidance"
    REGULATION = "regulation"
    ACT = "act"
    MONOGRAPH = "monograph"
    GENERAL_CHAPTER = "general_chapter"
    TEMPLATE = "template"
    Q_AND_A = "q_and_a"
    OTHER = "other"
    SYNTHETIC_TEST = "synthetic_test"  # placeholder data only, never real evidence


class ApplicabilityStatus(str, Enum):
    CURRENT = "current"
    SUPERSEDED = "superseded"
    DRAFT = "draft"
    WITHDRAWN = "withdrawn"
    UNKNOWN = "unknown"


class QAStatus(str, Enum):
    """Team QA labels. Member 2 agents never emit VERIFIED - only Member 5's
    QA/Critic and the human assessor can raise a finding to verified."""

    VERIFIED = "verified"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"
    HUMAN_REVIEW = "human-review"


class EvidenceStatus(str, Enum):
    """Why the evidence looks the way it does (finer-grained than QA status)."""

    CANDIDATE_EVIDENCE_FOUND = "candidate_evidence_found"
    EMPTY_KNOWLEDGE_BASE = "empty_knowledge_base"
    NO_PASSAGES_RETRIEVED = "no_passages_retrieved"
    RETRIEVED_NOT_RELEVANT = "retrieved_not_relevant"
    NOT_APPLICABLE = "not_applicable"  # e.g. pure numerical comparison findings


REQUIRED_PROVENANCE_FIELDS = (
    "document_version",
    "page_number",
    "publication_or_effective_date",
)


# ---------------------------------------------------------------------------
# 1. Input contract with Member 3
# ---------------------------------------------------------------------------
class PassageMetadata(BaseModel):
    """Source/provenance metadata attached to every stored passage."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    chunk_id: str
    source_title: str = Field(min_length=1, max_length=500)
    issuing_organization: str = Field(min_length=1, max_length=100)
    source_identifier: str = Field(
        min_length=1,
        max_length=500,
        description="Official URL or document identifier (e.g. 'ICH Q6A').",
    )
    document_version: str | None = Field(default=None, max_length=100)
    publication_date: str | None = None
    effective_date: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    page_label: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9.\-]{1,20}$",
        description="Page number PRINTED on the page (e.g. '3', 'iv', '317'); page_number is the PDF page.",
    )
    ctd_section: str | None = None
    document_type: DocumentType
    content_hash: str
    applicability_status: ApplicabilityStatus = ApplicabilityStatus.UNKNOWN
    chunk_index: int | None = Field(default=None, ge=0)
    chunk_size: int | None = Field(default=None, ge=1, description="Chunker setting (tokens/chars)")
    chunk_overlap: int | None = Field(default=None, ge=0)
    language: str | None = Field(default=None, max_length=20)

    @field_validator("chunk_id")
    @classmethod
    def _check_chunk_id(cls, value: str) -> str:
        if not _CHUNK_ID_RE.match(value):
            raise ValueError(
                "chunk_id may only contain letters, digits, '.', '_', ':', '-' (max 200 chars)"
            )
        return value

    @field_validator("source_title", "issuing_organization", "source_identifier")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("publication_date", "effective_date")
    @classmethod
    def _check_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not _PARTIAL_DATE_RE.match(value):
            raise ValueError("dates must be ISO format YYYY, YYYY-MM or YYYY-MM-DD")
        return value

    @field_validator("ctd_section")
    @classmethod
    def _check_ctd(cls, value: str | None) -> str | None:
        return normalise_ctd_section(value)

    @field_validator("content_hash")
    @classmethod
    def _check_hash(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("content_hash must be a 64-character lowercase SHA-256 hex digest")
        return value

    # -- provenance ---------------------------------------------------------
    def missing_provenance(self) -> list[str]:
        """Optional provenance fields that are absent for this passage."""
        missing: list[str] = []
        if not self.document_version:
            missing.append("document_version")
        if self.page_number is None:
            missing.append("page_number")
        if not (self.publication_date or self.effective_date):
            missing.append("publication_or_effective_date")
        if self.applicability_status == ApplicabilityStatus.UNKNOWN:
            missing.append("applicability_status")
        return missing

    @property
    def provenance_complete(self) -> bool:
        return not self.missing_provenance()


class PassageRecord(BaseModel):
    """One processed passage as delivered by Member 3's ingestion pipeline.

    `chunk_id` and `content_hash` are optional on input: if absent they are
    generated deterministically. If `content_hash` IS supplied it must match the
    text, which catches corruption between pipelines.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str | None = None
    text: str = Field(min_length=1, max_length=20000)
    source_title: str
    issuing_organization: str
    source_identifier: str
    document_version: str | None = None
    publication_date: str | None = None
    effective_date: str | None = None
    page_number: int | None = None
    page_label: str | None = None
    ctd_section: str | None = None
    document_type: DocumentType
    content_hash: str | None = None
    applicability_status: ApplicabilityStatus = ApplicabilityStatus.UNKNOWN
    chunk_index: int | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    language: str | None = None

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("passage text must not be blank")
        return value

    @model_validator(mode="after")
    def _fill_ids(self) -> PassageRecord:
        actual_hash = compute_content_hash(self.text)
        if self.content_hash is not None and self.content_hash.lower() != actual_hash:
            raise ValueError("content_hash does not match the passage text (data corrupted?)")
        self.content_hash = actual_hash
        if self.chunk_id is None:
            self.chunk_id = make_chunk_id(
                self.source_identifier.strip(),
                self.document_version,
                self.page_number,
                self.chunk_index,
                actual_hash,
            )
        return self

    def to_metadata(self) -> PassageMetadata:
        """Split off the provenance metadata (validates it fully)."""
        data = self.model_dump(exclude={"text"})
        return PassageMetadata(**data)


# ---------------------------------------------------------------------------
# 2. Retrieval contract
# ---------------------------------------------------------------------------
class SearchFilters(BaseModel):
    """Metadata filters applied inside ChromaDB before similarity ranking."""

    model_config = ConfigDict(extra="forbid")

    ctd_sections: list[str] = Field(default_factory=list)
    include_parent_sections: bool = Field(
        default=True,
        description="Also match passages tagged with a parent heading (3.2.S.4 -> 3.2.S, 3.2).",
    )
    document_types: list[DocumentType] = Field(default_factory=list)
    issuing_organizations: list[str] = Field(default_factory=list)
    applicability_statuses: list[ApplicabilityStatus] = Field(default_factory=list)

    @field_validator("ctd_sections")
    @classmethod
    def _norm_sections(cls, values: list[str]) -> list[str]:
        out = []
        for value in values:
            norm = normalise_ctd_section(value)
            if norm:
                out.append(norm)
        return out

    def is_empty(self) -> bool:
        return not (
            self.ctd_sections
            or self.document_types
            or self.issuing_organizations
            or self.applicability_statuses
        )


class RetrievedPassage(BaseModel):
    """A passage returned by retrieval, with its untouched source metadata.

    `retrieval_score` = cosine similarity from the embedding search.
    `rerank_score` = raw cross-encoder relevance score (a logit, NOT a
    probability, NOT evidence of regulatory correctness).
    `retrieval_method` = "direct_lookup" when a passage was fetched by its
    chunk_id (e.g. a cited regulatory limit) rather than found by search; such
    passages have no retrieval score.
    """

    chunk_id: str
    text: str
    metadata: PassageMetadata
    retrieval_method: Literal["vector_search", "direct_lookup"] = "vector_search"
    retrieval_score: float | None = None
    retrieval_rank: int | None = Field(default=None, ge=1)
    rerank_score: float | None = None
    rerank_rank: int | None = Field(default=None, ge=1)
    untrusted_content_flags: list[str] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    query_fingerprint: str
    filters: SearchFilters
    knowledge_base_size: int
    candidates_considered: int
    reranked: bool
    embedding_model: str
    reranker_model: str | None
    passages: list[RetrievedPassage]
    latency_ms: float

    @property
    def is_empty_knowledge_base(self) -> bool:
        return self.knowledge_base_size == 0


# ---------------------------------------------------------------------------
# 3. Team finding contract
# ---------------------------------------------------------------------------
class SponsorEvidence(BaseModel):
    """Evidence taken from the sponsor's dossier. Treated as CONFIDENTIAL.

    `content` is hidden from repr() and from `Finding.model_dump_redacted()`
    and is never logged.
    """

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=200)
    ctd_section: str | None = None
    description: str = Field(default="", max_length=500, description="Short non-confidential label")
    document_reference: str | None = Field(default=None, description="e.g. 'S.4.1 Table 1, p.12'")
    content: str | None = Field(default=None, repr=False)
    confidential: bool = True

    @field_validator("ctd_section")
    @classmethod
    def _check_ctd(cls, value: str | None) -> str | None:
        return normalise_ctd_section(value)


class Citation(BaseModel):
    """Provenance for one regulatory passage. Built ONLY from stored metadata,
    so a citation can never point to a source that is not in the knowledge base."""

    chunk_id: str
    source_title: str
    issuing_organization: str
    source_identifier: str
    document_version: str | None
    publication_date: str | None
    effective_date: str | None
    page_number: int | None
    ctd_section: str | None
    document_type: DocumentType
    applicability_status: ApplicabilityStatus
    content_hash: str
    provenance_complete: bool
    missing_provenance: list[str]
    page_label: str | None = None  # printed page number; page_number is the PDF page

    @classmethod
    def from_metadata(cls, meta: PassageMetadata) -> Citation:
        return cls(
            chunk_id=meta.chunk_id,
            source_title=meta.source_title,
            issuing_organization=meta.issuing_organization,
            source_identifier=meta.source_identifier,
            document_version=meta.document_version,
            publication_date=meta.publication_date,
            effective_date=meta.effective_date,
            page_number=meta.page_number,
            page_label=meta.page_label,
            ctd_section=meta.ctd_section,
            document_type=meta.document_type,
            applicability_status=meta.applicability_status,
            content_hash=meta.content_hash,
            provenance_complete=meta.provenance_complete,
            missing_provenance=meta.missing_provenance(),
        )

    def short_label(self) -> str:
        parts = [self.issuing_organization, self.source_title]
        if self.document_version:
            parts.append(version_label(self.document_version))
        if self.page_number is not None:
            parts.append(page_text(self.page_number, self.page_label))
        return ", ".join(parts)


def page_text(page_number: int | None, page_label: str | None) -> str:
    """'p.3 (PDF p.7)' when the printed page differs from the PDF page, else 'p.7'."""
    if page_number is None:
        return "p.n/a"
    if page_label and page_label != str(page_number):
        return f"p.{page_label} (PDF p.{page_number})"
    return f"p.{page_number}"


def version_label(version: str) -> str:
    """'1.0' -> 'version 1.0'; 'Step 4' and 'Final Version (Step 4)' stay as written."""
    return f"version {version}" if version[:1].isdigit() else version


class Finding(BaseModel):
    """The single structured object every agent returns to the Orchestrator."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    finding_id: str = Field(default_factory=lambda: f"F-{uuid.uuid4().hex[:12]}")
    agent_name: str
    ctd_section: str
    assessment_question: str
    sponsor_evidence: list[SponsorEvidence] = Field(default_factory=list)
    regulatory_evidence: list[RetrievedPassage] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    conclusion: str
    rationale: str
    uncertainty: str
    qa_status: QAStatus
    evidence_status: EvidenceStatus
    requires_human_review: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @field_validator("ctd_section")
    @classmethod
    def _check_ctd(cls, value: str) -> str:
        norm = normalise_ctd_section(value)
        if norm is None:
            raise ValueError("ctd_section is required")
        return norm

    @model_validator(mode="after")
    def _citations_match_evidence(self) -> Finding:
        evidence_ids = {p.chunk_id for p in self.regulatory_evidence}
        citation_ids = {c.chunk_id for c in self.citations}
        if citation_ids - evidence_ids:
            raise ValueError(
                "citations reference passages that are not in regulatory_evidence: "
                f"{sorted(citation_ids - evidence_ids)}"
            )
        if evidence_ids - citation_ids:
            raise ValueError(
                f"regulatory_evidence without citations: {sorted(evidence_ids - citation_ids)}"
            )
        return self

    def model_dump_redacted(self) -> dict[str, Any]:
        """JSON-safe dump with confidential sponsor content removed (for logs,
        benchmark outputs and anything leaving the assessor's environment)."""
        data = self.model_dump(mode="json")
        for item in data.get("sponsor_evidence", []):
            if item.get("content") is not None:
                item["content"] = "[REDACTED]"
        for key in list(data.get("metadata", {})):
            if key.startswith(CONFIDENTIAL_METADATA_PREFIX):
                data["metadata"][key] = "[REDACTED]"
        return data


# Metadata keys starting with this prefix hold sponsor-derived values (e.g.
# batch results) and are removed by `Finding.model_dump_redacted()`.
CONFIDENTIAL_METADATA_PREFIX = "confidential_"


class AgentRequest(BaseModel):
    """Uniform input every agent's `run()` accepts from the Orchestrator."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(default_factory=lambda: f"T-{uuid.uuid4().hex[:12]}")
    ctd_section: str
    assessment_question: str = Field(min_length=1, max_length=2000)
    sponsor_evidence: list[SponsorEvidence] = Field(default_factory=list)
    filters: SearchFilters | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("ctd_section")
    @classmethod
    def _check_ctd(cls, value: str) -> str:
        norm = normalise_ctd_section(value)
        if norm is None:
            raise ValueError("ctd_section is required")
        return norm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalise_ctd_section(value: str | None) -> str | None:
    """Normalise and validate a CTD section string ('3.2.s.4' -> '3.2.S.4')."""
    if value is None:
        return None
    cleaned = value.strip().rstrip(".")
    if cleaned.lower().startswith("module "):
        cleaned = cleaned[len("module ") :].strip()
    if not cleaned:
        return None
    cleaned = cleaned.upper().replace(" ", "")
    if not _CTD_RE.match(cleaned):
        raise ValueError(f"invalid CTD section {value!r}; expected e.g. '3.2.S.4.1'")
    return cleaned


def ctd_ancestors(section: str) -> list[str]:
    """Parent headings of a CTD section, most specific first.

    '3.2.S.4.1' -> ['3.2.S.4', '3.2.S', '3.2']  (stops at the module heading).

    The module heading ('3.2') is included because some guidelines (e.g. the
    SAHPRA Quality and Bioequivalence guideline) are organised by procedure
    rather than by CTD section, so their general pages are tagged '3.2'.
    Without it, a filter for any 3.2.S subsection silently excluded them.
    """
    parts = section.split(".")
    letter_idx = next((i for i, p in enumerate(parts) if p.isalpha()), None)
    stop = letter_idx if letter_idx is not None else 1
    return [".".join(parts[:i]) for i in range(len(parts) - 1, stop - 1, -1)]
