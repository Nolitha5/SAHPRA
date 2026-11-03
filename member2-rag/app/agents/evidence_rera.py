"""Evidence/RERA agent (Regulatory Evidence Retrieval & Attribution).

Given an assessment question and a CTD section, it:
1. calls the shared RetrievalService (filtered to the section + its parents),
2. applies the shared evidence rules (relevance gate, outdated/draft sources,
   version conflicts, missing provenance, synthetic data, untrusted text),
3. returns ONE structured `Finding` with every supporting passage and a
   citation built from stored metadata.

What it deliberately does NOT do:
* It does not write regulatory requirements in its own words (no LLM), so it
  cannot invent requirements or citations.
* It never says a dossier is compliant, and never emits QA status "verified".
* It does not call other agents; the Orchestrator (Member 1) routes findings.
"""

from __future__ import annotations

from app.agents.common import (
    assess_evidence,
    below_threshold_summary,
    evidence_conclusion,
    evidence_rationale,
    explain_uncertainty,
)
from app.config import Settings
from app.logging_utils import get_logger, log_event
from app.retrieval.retrieval_service import RetrievalService
from app.schemas import (
    AgentRequest,
    Finding,
    QAStatus,
    SearchFilters,
    SponsorEvidence,
    normalise_ctd_section,
)

logger = get_logger("agents.evidence_rera")

AGENT_NAME = "evidence_rera"


class EvidenceReraAgent:
    name = AGENT_NAME

    def __init__(self, retrieval: RetrievalService, settings: Settings | None = None) -> None:
        self.retrieval = retrieval
        self.settings = settings or retrieval.settings

    def assess(
        self,
        question: str,
        ctd_section: str,
        sponsor_evidence: list[SponsorEvidence] | None = None,
        filters: SearchFilters | None = None,
        use_section_filter: bool = True,
        use_reranker: bool | None = None,
    ) -> Finding:
        """Retrieve and attribute regulatory evidence for one question.

        Raises InvalidQueryError for an empty/oversized question and ValueError
        for an invalid CTD section.
        """
        section = normalise_ctd_section(ctd_section)
        if section is None:
            raise ValueError("ctd_section is required")

        effective_filters = filters.model_copy(deep=True) if filters else SearchFilters()
        if use_section_filter and not effective_filters.ctd_sections:
            effective_filters = effective_filters.model_copy(update={"ctd_sections": [section]})

        result = self.retrieval.retrieve(question, filters=effective_filters, use_reranker=use_reranker)
        assessment = assess_evidence(result, self.settings)

        finding = Finding(
            agent_name=self.name,
            ctd_section=section,
            assessment_question=question.strip(),
            sponsor_evidence=list(sponsor_evidence or []),
            regulatory_evidence=assessment.supporting,
            citations=assessment.citations,
            conclusion=evidence_conclusion(assessment),
            rationale=evidence_rationale(assessment, result),
            uncertainty=explain_uncertainty(assessment, result.reranked),
            qa_status=assessment.qa_status,
            evidence_status=assessment.evidence_status,
            requires_human_review=True,
            metadata={
                "flags": assessment.flags,
                "version_conflicts": assessment.version_conflicts,
                "below_threshold_candidates": below_threshold_summary(assessment.below_threshold),
                "retrieval": {
                    "query_fingerprint": result.query_fingerprint,
                    "filters": effective_filters.model_dump(mode="json"),
                    "knowledge_base_size": result.knowledge_base_size,
                    "candidates_considered": result.candidates_considered,
                    "reranked": result.reranked,
                    "embedding_model": result.embedding_model,
                    "reranker_model": result.reranker_model,
                    "latency_ms": result.latency_ms,
                    "thresholds": {
                        "min_rerank_score": self.settings.min_rerank_score,
                        "min_retrieval_score": self.settings.min_retrieval_score,
                    },
                },
            },
        )
        if finding.qa_status == QAStatus.VERIFIED:  # invariant: Member 2 never verifies
            raise RuntimeError("Evidence/RERA must not emit a 'verified' finding")
        log_event(
            logger,
            20,
            "evidence_finding_created",
            finding_id=finding.finding_id,
            ctd_section=section,
            qa_status=finding.qa_status.value,
            evidence_status=finding.evidence_status.value,
            passages=len(finding.regulatory_evidence),
            sponsor_items=len(finding.sponsor_evidence),
        )
        return finding

    def run(self, request: AgentRequest) -> list[Finding]:
        """Uniform Orchestrator entry point (same shape for every agent)."""
        return [
            self.assess(
                question=request.assessment_question,
                ctd_section=request.ctd_section,
                sponsor_evidence=request.sponsor_evidence,
                filters=request.filters,
                use_section_filter=bool(request.parameters.get("use_section_filter", True)),
                use_reranker=request.parameters.get("use_reranker"),
            )
        ]
