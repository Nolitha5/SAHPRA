"""
Shared helpers for M3's S.2 / S.3 specialist agents.

Both agents consume the DossierChunk objects the ingestion pipeline produces
and emit Finding objects in the team's shared schema. They work on sponsor
content only (completeness / internal-consistency checks); regulatory
comparison against ICH/SAHPRA/pharmacopoeia happens once M2's Evidence/RERA
service is wired in (findings carry regulatory_evidence=[] until then).
"""
from __future__ import annotations

import hashlib

from .schemas import DossierChunk, Finding, FindingStatus, SponsorEvidence


def chunks_in_section(chunks: list[DossierChunk], prefix: str) -> list[DossierChunk]:
    """Chunks whose CTD section falls under `prefix` (e.g. '3.2.S.2'),
    excluding anything the pipeline already flagged as unreadable."""
    p = prefix.upper()
    return [
        c
        for c in chunks
        if c.ctd_section.upper().startswith(p) and not c.quality_flag
    ]


def present_subsections(chunks: list[DossierChunk]) -> set[str]:
    """Set of distinct CTD section codes present among the given chunks."""
    return {c.ctd_section.upper() for c in chunks}


def make_finding_id(agent_id: str, case_id: str, tag: str) -> str:
    raw = f"{agent_id}|{case_id}|{tag}"
    return "F-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def evidence_from_chunk(chunk: DossierChunk, max_chars: int = 400) -> SponsorEvidence:
    passage = chunk.text.strip()
    if len(passage) > max_chars:
        passage = passage[:max_chars].rstrip() + " …"
    return SponsorEvidence(
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        ctd_section=chunk.ctd_section,
        passage=passage,
        page=chunk.page,
    )


def missing_subsection_finding(
    agent_id: str,
    case_id: str,
    section_code: str,
    section_title: str,
    sibling_evidence: list[SponsorEvidence],
) -> Finding:
    """A MISSING_INFORMATION finding for a required CTD subsection that no
    chunk could be attributed to. Never asserts the subsection is truly
    absent from the dossier — only that ingestion found no content for it,
    which is itself something the assessor must see."""
    return Finding(
        finding_id=make_finding_id(agent_id, case_id, f"missing-{section_code}"),
        case_id=case_id,
        agent_id=agent_id,
        ctd_section=section_code,
        issue_type="missing_subsection",
        status=FindingStatus.MISSING_INFORMATION,
        sponsor_evidence=sibling_evidence,
        rationale=(
            f"No content was attributed to {section_code} "
            f"({section_title}) during ingestion. Either the subsection is "
            f"absent from the dossier or its heading was not recognised. "
            f"Requires assessor confirmation."
        ),
        uncertainty=0.5,
        attributes={"check": "completeness", "expected_section": section_code},
    )
