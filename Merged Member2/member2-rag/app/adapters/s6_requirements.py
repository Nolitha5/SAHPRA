"""M2 side of the S.6 Container Closure Agent's `RequirementSource` port.

The S.6 agent (branch `thobeka-s6-container-closure`, `src/container_closure/ports.py`)
asks for requirements with:

    get_requirements(topic: str) -> Sequence[RKBRequirement]

This module does everything M2 is responsible for and returns plain dicts with exactly
the fields of S.6's `RKBRequirement` / `SourceReference`, so this package never imports
S.6 code. S.6's adapter is then only:

    from app.adapters.s6_requirements import S6RequirementSource
    m2_source = S6RequirementSource(m2.retrieval)

    class M2RequirementSource:                       # S.6 code, implements RequirementSource
        def get_requirements(self, topic):
            try:
                rows = m2_source.get_requirements(topic)
            except Exception as exc:                 # M2 unavailable / invalid topic
                raise PortError(str(exc)) from exc
            return [RKBRequirement.model_validate(r) for r in rows]

What M2 does here
-----------------
1. Turns the topic (a component name, storage descriptor or keyword taken from an S.6
   claim) into a focused question, unless the topic is already a question.
2. Searches twice and merges by chunk_id:
   * filtered to CTD 3.2.S.6 (with its parent headings 3.2.S and 3.2), and
   * unfiltered, because no guideline in the knowledge base is tagged 3.2.S.6 and
     container-closure text also sits in guidance tagged 3.2.S.7 (ICH Q1A(R2)) and
     3.2.P.2 (ICH Q8(R2)), which the filter excludes.
3. Keeps only passages that pass M2's relevance gate (`is_relevant_enough`), so a weak
   match never becomes a "requirement". An empty list means "no evidence found": S.6
   reports INSUFFICIENT_DATA, it must not read it as "no requirement exists".

Each returned item is a cited regulatory PASSAGE that may contain a requirement. It is
not a validated, atomic requirement and it is not a compliance decision.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from app.agents.common import is_relevant_enough
from app.config import Settings
from app.retrieval.retrieval_service import RetrievalService
from app.schemas import RetrievedPassage, SearchFilters

S6_SECTION = "3.2.S.6"
SOURCE_TYPE = "m2_rkb"  # S.6's SourceReference.source_type for M2 results


def topic_to_question(topic: str) -> str:
    """A focused retrieval question for an S.6 topic (kept as is if it already is a question)."""
    cleaned = " ".join(topic.split())
    if not cleaned:
        raise ValueError("topic must not be empty")
    if cleaned.endswith("?"):
        return cleaned
    return (
        f"What regulatory guidance applies to {cleaned} in the container closure system "
        f"of the drug substance (CTD {S6_SECTION})?"
    )


def format_citation(p: RetrievedPassage) -> str:
    """e.g. 'ICH M4Q(R1) (Step 4), p. 11 (PDF p. 19), CTD 3.2'."""
    m = p.metadata
    out = m.source_identifier
    if m.document_version:
        out += f" ({m.document_version})"
    if m.page_label and m.page_number and m.page_label != str(m.page_number):
        out += f", p. {m.page_label} (PDF p. {m.page_number})"
    elif m.page_number:
        out += f", p. {m.page_number}"
    if m.ctd_section:
        out += f", CTD {m.ctd_section}"
    return out


def to_rkb_requirement(p: RetrievedPassage) -> dict[str, Any]:
    """One passage in the shape of S.6's `RKBRequirement` (with a nested `SourceReference`)."""
    m = p.metadata
    section = m.ctd_section or "unspecified"
    document = m.source_title + (f" ({m.document_version})" if m.document_version else "")
    return {
        "requirement_id": p.chunk_id,
        "guideline": m.source_identifier,
        "section": section,
        "text": p.text,
        "citation": format_citation(p),
        "source_ref": {
            "source_type": SOURCE_TYPE,
            "source_id": p.chunk_id,
            "section": section,
            "document": document,
            "page": m.page_number,
            "field_path": None,
        },
    }


def _score(p: RetrievedPassage) -> float:
    if p.rerank_score is not None:
        return p.rerank_score
    return p.retrieval_score if p.retrieval_score is not None else float("-inf")


@dataclass
class S6RequirementSearch:
    """Full result for audit/logging on the S.6 side: requirements plus how they were found."""

    topic: str
    question: str
    requirements: list[dict[str, Any]]
    scores: dict[str, float]  # requirement_id -> rerank (or retrieval) score; not a probability
    below_threshold: int  # passages found but too weak to return
    knowledge_base_size: int
    searches: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "question": self.question,
            "requirements": self.requirements,
            "scores": self.scores,
            "below_threshold": self.below_threshold,
            "knowledge_base_size": self.knowledge_base_size,
            "searches": self.searches,
        }


class S6RequirementSource:
    """M2 implementation behind S.6's `RequirementSource.get_requirements(topic)`."""

    def __init__(
        self,
        retrieval: RetrievalService,
        settings: Settings | None = None,
        max_requirements: int | None = None,
        broaden: bool = True,
    ) -> None:
        self.retrieval = retrieval
        self.settings = settings or retrieval.settings
        self.max_requirements = max_requirements or self.settings.final_k
        self.broaden = broaden

    def search(self, topic: str) -> S6RequirementSearch:
        question = topic_to_question(topic)
        runs: list[tuple[str, SearchFilters | None]] = [
            ("ctd_3.2.S.6_with_parents", SearchFilters(ctd_sections=[S6_SECTION]))
        ]
        if self.broaden:
            runs.append(("all_guidelines", None))

        best: dict[str, RetrievedPassage] = {}
        weak: set[str] = set()
        searches: list[dict[str, Any]] = []
        kb_size = 0
        for name, filters in runs:
            result = self.retrieval.retrieve(question, filters=filters)
            kb_size = result.knowledge_base_size
            kept = 0
            for p in result.passages:
                if not is_relevant_enough(p, self.settings):
                    weak.add(p.chunk_id)
                    continue
                kept += 1
                if p.chunk_id not in best or _score(p) > _score(best[p.chunk_id]):
                    best[p.chunk_id] = p
            searches.append({"search": name, "returned": len(result.passages), "relevant": kept,
                             "reranked": result.reranked, "query_fingerprint": result.query_fingerprint})

        ranked = sorted(best.values(), key=_score, reverse=True)[: self.max_requirements]
        return S6RequirementSearch(
            topic=topic,
            question=question,
            requirements=[to_rkb_requirement(p) for p in ranked],
            scores={p.chunk_id: round(_score(p), 4) for p in ranked},
            below_threshold=len(weak - best.keys()),
            knowledge_base_size=kb_size,
            searches=searches,
        )

    def get_requirements(self, topic: str) -> list[dict[str, Any]]:
        """Matches S.6's port: `RKBRequirement`-shaped dicts, best first; [] when nothing relevant."""
        return self.search(topic).requirements


def requirements_from_passages(passages: Sequence[RetrievedPassage]) -> list[dict[str, Any]]:
    """Convert passages S.6 already has (e.g. from an Evidence/RERA finding) without a new search."""
    return [to_rkb_requirement(p) for p in passages]
