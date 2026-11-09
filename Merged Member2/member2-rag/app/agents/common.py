"""Evidence-assessment logic shared by Evidence/RERA and S.4 Control.

Why a shared module (not in the original folder plan): both agents must apply
*identical* rules for deciding when evidence is sufficient, outdated or
conflicting. Agents are not allowed to call each other (the Orchestrator is the
hub), so the shared rules live here as plain functions instead.

Design principles enforced here:
* Deterministic, rule-based decisions - no LLM writes conclusions, so nothing
  can be invented. Conclusions only describe what was retrieved.
* Member 2 agents NEVER output QAStatus.VERIFIED. Only Member 5's QA/Critic
  and the human assessor can verify.
* Every regulatory passage in a finding carries a citation built from stored
  metadata (enforced again by the `Finding` validator).
* Scores are used only to decide what to *show* an assessor, never to decide
  compliance.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.config import Settings
from app.schemas import (
    ApplicabilityStatus,
    Citation,
    DocumentType,
    EvidenceStatus,
    QAStatus,
    RetrievalResult,
    RetrievedPassage,
    version_label,
)

_OUTDATED = {ApplicabilityStatus.SUPERSEDED, ApplicabilityStatus.WITHDRAWN}

ABSENCE_DISCLAIMER = (
    "Absence of retrieved passages does not prove that no relevant regulation or guideline "
    "exists; the knowledge base may be incomplete or the question may need rephrasing."
)
NOT_A_COMPLIANCE_DECISION = (
    "Retrieval of a relevant passage does not establish that the dossier is compliant. "
    "The final regulatory decision rests with the qualified human assessor."
)


@dataclass
class EvidenceAssessment:
    """Outcome of applying the shared evidence rules to one RetrievalResult."""

    supporting: list[RetrievedPassage]
    below_threshold: list[RetrievedPassage]
    evidence_status: EvidenceStatus
    qa_status: QAStatus
    flags: list[str] = field(default_factory=list)
    version_conflicts: dict[str, list[str]] = field(default_factory=dict)

    @property
    def citations(self) -> list[Citation]:
        return [Citation.from_metadata(p.metadata) for p in self.supporting]


def is_relevant_enough(passage: RetrievedPassage, settings: Settings) -> bool:
    """Heuristic gate for showing a passage as candidate evidence."""
    if passage.rerank_score is not None:
        return passage.rerank_score >= settings.min_rerank_score
    if passage.retrieval_score is not None:
        return passage.retrieval_score >= settings.min_retrieval_score
    return True  # direct lookups were explicitly cited by a person/upstream step


def _doc_key(p: RetrievedPassage) -> str:
    m = p.metadata
    return f"{m.issuing_organization.strip().lower()}|{m.source_title.strip().lower()}"


def detect_version_conflicts(passages: Sequence[RetrievedPassage]) -> dict[str, list[str]]:
    """Same document (organisation + title) present in more than one version."""
    versions: dict[str, set[str]] = defaultdict(set)
    labels: dict[str, str] = {}
    for p in passages:
        key = _doc_key(p)
        versions[key].add(p.metadata.document_version or "unknown")
        labels[key] = f"{p.metadata.issuing_organization}: {p.metadata.source_title}"
    return {labels[k]: sorted(v) for k, v in versions.items() if len(v) > 1}


def assess_evidence(result: RetrievalResult, settings: Settings) -> EvidenceAssessment:
    """Apply the team's evidence rules to a retrieval result."""
    if result.is_empty_knowledge_base:
        return EvidenceAssessment([], [], EvidenceStatus.EMPTY_KNOWLEDGE_BASE, QAStatus.UNSUPPORTED,
                                  ["knowledge_base_empty"])
    if not result.passages:
        return EvidenceAssessment([], [], EvidenceStatus.NO_PASSAGES_RETRIEVED, QAStatus.UNSUPPORTED,
                                  ["no_passages_matched_filters"])

    supporting = [p for p in result.passages if is_relevant_enough(p, settings)]
    below = [p for p in result.passages if not is_relevant_enough(p, settings)]
    if not supporting:
        return EvidenceAssessment([], below, EvidenceStatus.RETRIEVED_NOT_RELEVANT,
                                  QAStatus.HUMAN_REVIEW, ["retrieved_passages_below_relevance_threshold"])

    flags: list[str] = []
    statuses = {p.metadata.applicability_status for p in supporting}
    if statuses & _OUTDATED:
        flags.append("contains_superseded_or_withdrawn_source")
    if ApplicabilityStatus.DRAFT in statuses:
        flags.append("contains_draft_source")
    if ApplicabilityStatus.UNKNOWN in statuses:
        flags.append("applicability_status_unknown_for_some_sources")
    if any(not p.metadata.provenance_complete for p in supporting):
        flags.append("incomplete_provenance_for_some_sources")
    if any(p.metadata.document_type == DocumentType.SYNTHETIC_TEST for p in supporting):
        flags.append("synthetic_test_data_not_real_evidence")
    if any(p.untrusted_content_flags for p in supporting):
        flags.append("instruction_like_text_in_retrieved_passage")
    conflicts = detect_version_conflicts(supporting)
    if conflicts:
        flags.append("multiple_versions_of_same_document")

    if conflicts:
        qa = QAStatus.CONFLICTING
    elif (
        all(p.metadata.applicability_status in _OUTDATED for p in supporting)
        or "synthetic_test_data_not_real_evidence" in flags
        or "instruction_like_text_in_retrieved_passage" in flags
    ):
        qa = QAStatus.HUMAN_REVIEW
    else:
        # Candidate evidence exists, but relevance is a heuristic and nothing
        # has been verified -> "partial" is the strongest label Member 2 gives.
        qa = QAStatus.PARTIAL

    return EvidenceAssessment(supporting, below, EvidenceStatus.CANDIDATE_EVIDENCE_FOUND, qa, flags, conflicts)


_FLAG_EXPLANATIONS = {
    "knowledge_base_empty": "The knowledge base contains no passages, so nothing could be retrieved.",
    "no_passages_matched_filters": "No passages matched the query within the selected filters.",
    "retrieved_passages_below_relevance_threshold": (
        "Passages were retrieved, but none reached the relevance threshold; they may not answer the question."
    ),
    "contains_superseded_or_withdrawn_source": "At least one source is marked superseded or withdrawn.",
    "contains_draft_source": "At least one source is a draft and may not be in force.",
    "applicability_status_unknown_for_some_sources": (
        "The applicability (current/superseded) of some sources is unknown in the metadata."
    ),
    "incomplete_provenance_for_some_sources": (
        "Some sources lack version, page or date metadata; their citations are incomplete."
    ),
    "synthetic_test_data_not_real_evidence": "Some passages are SYNTHETIC TEST DATA and are not regulatory evidence.",
    "instruction_like_text_in_retrieved_passage": (
        "A retrieved passage contains instruction-like text; it was treated strictly as data."
    ),
    "multiple_versions_of_same_document": "The same document appears in more than one version.",
}


def explain_uncertainty(assessment: EvidenceAssessment, reranked: bool) -> str:
    """Plain-English uncertainty statement for the finding."""
    lines = [_FLAG_EXPLANATIONS.get(f, f) for f in assessment.flags]
    if assessment.version_conflicts:
        for doc, versions in assessment.version_conflicts.items():
            lines.append(f"Versions found for {doc}: {', '.join(versions)}.")
    if assessment.evidence_status in {
        EvidenceStatus.EMPTY_KNOWLEDGE_BASE,
        EvidenceStatus.NO_PASSAGES_RETRIEVED,
    }:
        lines.append(ABSENCE_DISCLAIMER)
    if assessment.supporting:
        scorer = "cross-encoder reranker" if reranked else "embedding similarity"
        lines.append(
            f"Relevance was judged by a {scorer} score against a configurable threshold; "
            "scores are not probabilities and do not show regulatory correctness."
        )
        lines.append("No automated check confirms that the passages fully answer the question.")
    return " ".join(lines)


def source_summary(passages: Sequence[RetrievedPassage]) -> str:
    """One entry per document with its pages, e.g. 'ICH, Q2 title, Step 4, pp. 5, 7, 18'.

    The full per-passage list is already in `citations`; repeating it here
    would only make the rationale harder to read.
    """
    # Pages are shown as printed in the document, with the PDF page in brackets when it
    # differs (e.g. "pp. 3 (PDF 7), 6 (PDF 10)").
    docs: dict[tuple[str, str, str | None], dict[int, str | None]] = {}
    for p in passages:
        m = p.metadata
        pages = docs.setdefault((m.issuing_organization, m.source_title, m.document_version), {})
        if m.page_number is not None:
            pages.setdefault(m.page_number, m.page_label)
    entries = []
    for (org, title, version), pages in docs.items():
        parts = [org, title] + ([version_label(version)] if version else [])
        if pages:
            shown = [
                f"{label} (PDF {pdf})" if label and label != str(pdf) else str(pdf)
                for pdf, label in sorted(pages.items())
            ]
            parts.append(("p. " if len(shown) == 1 else "pp. ") + ", ".join(shown))
        entries.append(", ".join(parts))
    return "; ".join(entries)


def evidence_conclusion(assessment: EvidenceAssessment) -> str:
    status = assessment.evidence_status
    if status == EvidenceStatus.EMPTY_KNOWLEDGE_BASE:
        return "Insufficient evidence: the regulatory knowledge base is empty."
    if status == EvidenceStatus.NO_PASSAGES_RETRIEVED:
        return "Insufficient evidence: no regulatory passages were retrieved for this question."
    if status == EvidenceStatus.RETRIEVED_NOT_RELEVANT:
        return (
            f"Insufficient evidence: {len(assessment.below_threshold)} passage(s) were retrieved but none "
            "was judged relevant enough to support an answer. Referred for human review."
        )
    n = len(assessment.supporting)
    prefix = {
        QAStatus.CONFLICTING: "Potentially conflicting regulatory evidence retrieved",
        QAStatus.HUMAN_REVIEW: "Regulatory evidence retrieved that requires human review",
    }.get(assessment.qa_status, "Candidate regulatory evidence retrieved")
    return f"{prefix}: {n} passage(s) for assessor review. This is not a compliance determination."


def evidence_rationale(assessment: EvidenceAssessment, result: RetrievalResult) -> str:
    base = (
        f"Searched {result.knowledge_base_size} indexed passage(s) with {result.embedding_model}"
        + (f", reranked with {result.reranker_model}" if result.reranked else "")
        + f"; {result.candidates_considered} candidate(s) considered."
    )
    if assessment.supporting:
        base += f" Supporting sources: {source_summary(assessment.supporting)}."
    base += " " + NOT_A_COMPLIANCE_DECISION
    return base


def below_threshold_summary(passages: Sequence[RetrievedPassage]) -> list[dict]:
    """Lightweight pointers to weak candidates (kept in finding metadata)."""
    return [
        {
            "chunk_id": p.chunk_id,
            "source": Citation.from_metadata(p.metadata).short_label(),
            "retrieval_score": p.retrieval_score,
            "rerank_score": p.rerank_score,
        }
        for p in passages
    ]
