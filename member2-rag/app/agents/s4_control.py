"""S.4 Control agent - CTD 3.2.S.4 Control of Drug Substance.

Implemented now
---------------
1. Regulatory evidence retrieval for one S.4 topic (specification, analytical
   procedures, method validation, batch analyses, justification of
   specification) through the SAME shared RetrievalService - no separate DB.
2. Sponsor evidence is carried in the finding but kept separate from
   regulatory evidence (and redacted in `model_dump_redacted()`).
3. Optional structured numerical comparisons (see `spec_comparison.py`):
   a. batch results vs the sponsor's own acceptance criteria;
   b. sponsor criteria vs a structured regulatory limit that cites a
      knowledge-base chunk.
   Missing/ambiguous criteria or units => "not_compared" + human review.

Future work (not implemented)
-----------------------------
* Automatic extraction of specification tables from the dossier (Member 3's
  table extraction will feed `AcceptanceCriterion` objects).
* Automatic extraction of numeric limits from regulatory passages (requires
  expert-validated parsing; until then regulatory limits must be supplied in
  structured form with a citation).
* Method-validation completeness checks against a validated parameter
  checklist, and statistical trend analysis of batch data.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import ValidationError

from app.agents.common import (
    assess_evidence,
    below_threshold_summary,
    evidence_conclusion,
    evidence_rationale,
    explain_uncertainty,
)
from app.agents.spec_comparison import (
    AcceptanceCriterion,
    BatchResult,
    ComparisonRow,
    Outcome,
    compare_batches,
    compare_spec_to_regulatory,
)
from app.config import Settings
from app.logging_utils import get_logger, log_event
from app.retrieval.retrieval_service import RetrievalService
from app.schemas import (
    CONFIDENTIAL_METADATA_PREFIX,
    AgentRequest,
    Citation,
    EvidenceStatus,
    Finding,
    QAStatus,
    RetrievedPassage,
    SearchFilters,
    SponsorEvidence,
)

logger = get_logger("agents.s4_control")

AGENT_NAME = "s4_control"


class S4Topic(str, Enum):
    SPECIFICATION = "specification"
    ANALYTICAL_PROCEDURES = "analytical_procedures"
    METHOD_VALIDATION = "method_validation"
    BATCH_ANALYSES = "batch_analyses"
    JUSTIFICATION_OF_SPECIFICATION = "justification_of_specification"
    GENERAL = "general"


# CTD 3.2.S.4 sub-section headings (ICH M4Q structure).
TOPIC_SECTIONS = {
    S4Topic.SPECIFICATION: "3.2.S.4.1",
    S4Topic.ANALYTICAL_PROCEDURES: "3.2.S.4.2",
    S4Topic.METHOD_VALIDATION: "3.2.S.4.3",
    S4Topic.BATCH_ANALYSES: "3.2.S.4.4",
    S4Topic.JUSTIFICATION_OF_SPECIFICATION: "3.2.S.4.5",
    S4Topic.GENERAL: "3.2.S.4",
}

_SECTION_TO_TOPIC = {v: k for k, v in TOPIC_SECTIONS.items()}


class S4ControlAgent:
    name = AGENT_NAME

    def __init__(self, retrieval: RetrievalService, settings: Settings | None = None) -> None:
        self.retrieval = retrieval
        self.settings = settings or retrieval.settings

    # ------------------------------------------------------------------
    def retrieve_evidence(
        self,
        question: str,
        topic: S4Topic = S4Topic.GENERAL,
        sponsor_evidence: list[SponsorEvidence] | None = None,
        filters: SearchFilters | None = None,
        use_reranker: bool | None = None,
    ) -> Finding:
        """Regulatory evidence finding for one S.4 topic."""
        section = TOPIC_SECTIONS[topic]
        effective = filters.model_copy(deep=True) if filters else SearchFilters()
        if not effective.ctd_sections:
            effective = effective.model_copy(update={"ctd_sections": [section]})
        result = self.retrieval.retrieve(question, filters=effective, use_reranker=use_reranker)
        assessment = assess_evidence(result, self.settings)
        return Finding(
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
            metadata={
                "s4_topic": topic.value,
                "flags": assessment.flags,
                "version_conflicts": assessment.version_conflicts,
                "below_threshold_candidates": below_threshold_summary(assessment.below_threshold),
                "retrieval": {
                    "query_fingerprint": result.query_fingerprint,
                    "filters": effective.model_dump(mode="json"),
                    "knowledge_base_size": result.knowledge_base_size,
                    "candidates_considered": result.candidates_considered,
                    "reranked": result.reranked,
                    "embedding_model": result.embedding_model,
                    "reranker_model": result.reranker_model,
                    "latency_ms": result.latency_ms,
                },
            },
        )

    # ------------------------------------------------------------------
    def compare_batch_results(
        self,
        specification: list[AcceptanceCriterion],
        batch_results: list[BatchResult],
        sponsor_evidence: list[SponsorEvidence] | None = None,
        question: str = "Are the reported batch results within the sponsor's stated acceptance criteria?",
    ) -> Finding:
        """Batch results (S.4.4) vs the sponsor's own specification (S.4.1)."""
        if not batch_results:
            raise ValueError("batch_results must not be empty")
        sponsor_specs = [c for c in specification if c.source == "sponsor_specification"]
        rows = compare_batches(sponsor_specs, batch_results)
        counts = _count(rows)
        problems = counts[Outcome.OUTSIDE_CRITERIA] + counts[Outcome.NOT_COMPARED]
        borderline = sum(r.borderline for r in rows)

        # Numerically consistent is still only "partial": nothing here is "verified".
        qa = QAStatus.HUMAN_REVIEW if problems or borderline else QAStatus.PARTIAL

        conclusion = (
            f"Batch results compared with the sponsor's stated acceptance criteria: "
            f"{counts[Outcome.WITHIN_CRITERIA]} within, {counts[Outcome.OUTSIDE_CRITERIA]} outside, "
            f"{counts[Outcome.NOT_COMPARED]} not compared"
            + (f", {borderline} borderline" if borderline else "")
            + ". This checks internal consistency only; it does not establish that the "
            "acceptance criteria themselves are acceptable to the regulator."
        )
        uncertainty_parts = []
        if counts[Outcome.NOT_COMPARED]:
            uncertainty_parts.append(
                "Some results could not be compared automatically (missing/ambiguous criteria, units "
                "or non-numeric values); see the comparison rows."
            )
        if counts[Outcome.OUTSIDE_CRITERIA]:
            uncertainty_parts.append(
                "Some results appear outside the stated criteria; data-entry, unit or rounding issues "
                "must be excluded by the assessor before drawing conclusions."
            )
        if borderline:
            uncertainty_parts.append("Borderline values depend on the applicable rounding convention.")
        uncertainty_parts.append("Comparisons use values exactly as supplied by upstream extraction.")

        return Finding(
            agent_name=self.name,
            ctd_section=TOPIC_SECTIONS[S4Topic.BATCH_ANALYSES],
            assessment_question=question,
            sponsor_evidence=list(sponsor_evidence or []),
            conclusion=conclusion,
            rationale=(
                "Rule-based comparison of each batch value with the matching sponsor criterion, with "
                "explicit unit handling (only identical units or explicit mass-fraction units are "
                "converted)."
            ),
            uncertainty=" ".join(uncertainty_parts),
            qa_status=qa,
            evidence_status=EvidenceStatus.NOT_APPLICABLE,
            metadata={
                "s4_topic": S4Topic.BATCH_ANALYSES.value,
                "comparison_counts": {k.value: v for k, v in counts.items()},
                f"{CONFIDENTIAL_METADATA_PREFIX}comparison_rows": [r.model_dump(mode="json") for r in rows],
            },
        )

    # ------------------------------------------------------------------
    def compare_with_regulatory_limits(
        self,
        specification: list[AcceptanceCriterion],
        regulatory_limits: list[AcceptanceCriterion],
        sponsor_evidence: list[SponsorEvidence] | None = None,
        question: str = "Are the sponsor's acceptance criteria at least as strict as the cited regulatory limits?",
    ) -> Finding:
        """Sponsor criteria vs structured regulatory limits that cite KB chunks."""
        reg = [c for c in regulatory_limits if c.source == "regulatory"]
        if not reg:
            raise ValueError("no regulatory limits supplied (source='regulatory')")
        cited_ids = sorted({c.citation_chunk_id for c in reg if c.citation_chunk_id})
        stored = {p.chunk_id: p for p in self.retrieval.store.get(cited_ids)}

        sponsor_by_test = {}
        for c in specification:
            if c.source == "sponsor_specification":
                sponsor_by_test.setdefault(c.test_name.strip().lower(), []).append(c)

        rows: list[ComparisonRow] = []
        for limit in reg:
            matches = sponsor_by_test.get(limit.test_name.strip().lower(), [])
            if len(matches) != 1:
                rows.append(ComparisonRow(
                    comparison="sponsor_spec_vs_regulatory", test_name=limit.test_name,
                    criterion_text=limit.criterion_text, criterion_unit=limit.unit,
                    citation_chunk_id=limit.citation_chunk_id, outcome=Outcome.NOT_COMPARED,
                    reason="no sponsor criterion for this test" if not matches
                    else "ambiguous: more than one sponsor criterion for this test",
                ))
                continue
            rows.append(compare_spec_to_regulatory(matches[0], limit, limit.citation_chunk_id in stored))

        evidence = [
            RetrievedPassage(
                chunk_id=p.chunk_id, text=p.text, metadata=p.metadata, retrieval_method="direct_lookup"
            )
            for p in stored.values()
        ]
        counts = _count(rows)
        cited_outdated_or_synthetic = any(
            p.metadata.document_type.value == "synthetic_test"
            or p.metadata.applicability_status.value in {"superseded", "withdrawn", "draft"}
            for p in evidence
        )
        if counts[Outcome.NOT_COMPARED] or counts[Outcome.LESS_STRICT] or cited_outdated_or_synthetic:
            qa = QAStatus.HUMAN_REVIEW
        else:
            qa = QAStatus.PARTIAL
        missing = [cid for cid in cited_ids if cid not in stored]
        uncertainty = (
            "Regulatory limits were supplied in structured form by a person or upstream step; this "
            "agent did not extract them from text. Their applicability to this drug substance must be "
            "confirmed by the assessor."
        )
        if missing:
            uncertainty += f" Cited chunk(s) not found in the knowledge base: {', '.join(missing)}."
        if cited_outdated_or_synthetic:
            uncertainty += (
                " At least one cited source is synthetic test data, draft, superseded or withdrawn."
            )
        return Finding(
            agent_name=self.name,
            ctd_section=TOPIC_SECTIONS[S4Topic.SPECIFICATION],
            assessment_question=question,
            sponsor_evidence=list(sponsor_evidence or []),
            regulatory_evidence=evidence,
            citations=[Citation.from_metadata(p.metadata) for p in evidence],
            conclusion=(
                f"Sponsor criteria compared with cited limits: {counts[Outcome.AT_LEAST_AS_STRICT]} at least as "
                f"strict, {counts[Outcome.LESS_STRICT]} less strict, {counts[Outcome.NOT_COMPARED]} not compared. "
                "This is not a compliance determination."
            ),
            rationale="Rule-based comparison of numeric limits with explicit unit handling.",
            uncertainty=uncertainty,
            qa_status=qa,
            evidence_status=EvidenceStatus.NOT_APPLICABLE,
            metadata={
                "s4_topic": S4Topic.SPECIFICATION.value,
                "comparison_counts": {k.value: v for k, v in counts.items()},
                f"{CONFIDENTIAL_METADATA_PREFIX}comparison_rows": [r.model_dump(mode="json") for r in rows],
            },
        )

    # ------------------------------------------------------------------
    def assess(
        self,
        question: str,
        topic: S4Topic | str = S4Topic.GENERAL,
        sponsor_evidence: list[SponsorEvidence] | None = None,
        specification: list[AcceptanceCriterion] | None = None,
        batch_results: list[BatchResult] | None = None,
        regulatory_limits: list[AcceptanceCriterion] | None = None,
        filters: SearchFilters | None = None,
        use_reranker: bool | None = None,
    ) -> list[Finding]:
        """Full S.4 workflow: evidence finding + any comparisons that have data."""
        topic = S4Topic(topic)
        findings = [self.retrieve_evidence(question, topic, sponsor_evidence, filters, use_reranker)]
        if batch_results:
            findings.append(self.compare_batch_results(specification or [], batch_results, sponsor_evidence))
        if regulatory_limits:
            findings.append(
                self.compare_with_regulatory_limits(specification or [], regulatory_limits, sponsor_evidence)
            )
        for f in findings:
            if f.qa_status == QAStatus.VERIFIED:
                raise RuntimeError("S.4 Control must not emit a 'verified' finding")
            log_event(logger, 20, "s4_finding_created", finding_id=f.finding_id, ctd_section=f.ctd_section,
                      qa_status=f.qa_status.value, evidence_status=f.evidence_status.value)
        return findings

    def run(self, request: AgentRequest) -> list[Finding]:
        """Uniform Orchestrator entry point.

        `request.parameters` may contain:
          topic: one of S4Topic values (default: derived from ctd_section)
          specification: list of AcceptanceCriterion dicts
          batch_results: list of BatchResult dicts
          regulatory_limits: list of AcceptanceCriterion dicts; `source` defaults to
            'regulatory' here, so each one must carry a citation_chunk_id
          use_reranker: bool
        """
        params: dict[str, Any] = request.parameters
        topic = params.get("topic") or _SECTION_TO_TOPIC.get(request.ctd_section, S4Topic.GENERAL)
        try:
            spec = [AcceptanceCriterion(**c) for c in params.get("specification", [])]
            batches = [BatchResult(**b) for b in params.get("batch_results", [])]
            # Without this default, a limit listed under regulatory_limits but lacking
            # source='regulatory' would be read as a sponsor limit and silently ignored.
            limits = [AcceptanceCriterion(**{"source": "regulatory", **c}) for c in params.get("regulatory_limits", [])]
        except ValidationError as exc:
            # Do not echo values (they may be confidential); report fields only.
            fields = sorted({".".join(map(str, e["loc"])) for e in exc.errors()})
            raise ValueError(f"invalid S.4 parameters in fields: {fields}") from None
        return self.assess(
            question=request.assessment_question,
            topic=topic,
            sponsor_evidence=request.sponsor_evidence,
            specification=spec,
            batch_results=batches,
            regulatory_limits=limits,
            filters=request.filters,
            use_reranker=params.get("use_reranker"),
        )


def _count(rows: list[ComparisonRow]) -> dict[Outcome, int]:
    counts = {o: 0 for o in Outcome}
    for r in rows:
        counts[r.outcome] += 1
    return counts
