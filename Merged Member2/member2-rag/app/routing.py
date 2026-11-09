"""Automatic routing for the dashboard's "just ask a question" search.

The user types only a question. This module
  1. searches ALL guidelines once (no CTD filter: the most complete setting in the benchmarks),
  2. lets the best-matching passages vote for a CTD section (each guideline carries the CTD
     tag of its scope, e.g. ICH Q2(R2) -> 3.2.S.4.3, ICH Q1A(R2) -> 3.2.S.7),
  3. picks the agent from that section: anything under 3.2.S.4 -> S.4 Control, otherwise
     Evidence/RERA, and hands it the SAME passages (no second search),
  4. returns the decision with its reason, so the assessor can see why.

No language model is involved; the decision is a weighted count. It is a dashboard
convenience: in the team pipeline, Member 1's Orchestrator decides which agent to call.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from app.agents.common import is_relevant_enough
from app.agents.evidence_rera import EvidenceReraAgent
from app.agents.s4_control import TOPIC_SECTIONS, S4ControlAgent, S4Topic
from app.config import Settings
from app.integration import Member2Components
from app.schemas import Finding, RetrievalResult, RetrievedPassage, SearchFilters

S4_PART = "3.2.S.4"
VOTERS = 5  # how many of the best passages vote
GENERAL_SECTION = "3.2"  # used when nothing was found
_SECTION_TO_TOPIC = {section: topic for topic, section in TOPIC_SECTIONS.items()}


def _in_s4(tag: str) -> bool:
    return tag == S4_PART or tag.startswith(S4_PART + ".")


@dataclass
class Route:
    agent: str  # "evidence_rera" | "s4_control"
    ctd_section: str
    reason: str
    votes: dict[str, float] = field(default_factory=dict)  # CTD tag -> weight
    based_on: list[str] = field(default_factory=list)  # e.g. "ICH Q2(R2) p.7 (3.2.S.4.3)"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def choose_route(result: RetrievalResult, settings: Settings) -> Route:
    """Pick the CTD section and agent from where the best passages come from."""
    relevant = [p for p in result.passages if is_relevant_enough(p, settings)]
    voters: list[RetrievedPassage] = (relevant or result.passages)[:VOTERS]
    if not voters:
        return Route("evidence_rera", GENERAL_SECTION,
                     "No passage matched the question, so Evidence/RERA reports that no evidence was found.")

    votes: dict[str, float] = defaultdict(float)
    for rank, p in enumerate(voters, start=1):
        votes[p.metadata.ctd_section or GENERAL_SECTION] += 1.0 / rank  # the best match counts most

    s4_weight = sum(w for tag, w in votes.items() if _in_s4(tag))
    other_weight = sum(w for tag, w in votes.items() if not _in_s4(tag))
    family = [t for t in votes if _in_s4(t) == (s4_weight > other_weight)]
    section = max(family, key=lambda t: (votes[t], t.count(".")))  # ties: the more specific heading

    based_on = [
        f"{p.metadata.source_identifier} p.{p.metadata.page_number} ({p.metadata.ctd_section or 'untagged'})"
        for p in voters
    ]
    agent = "s4_control" if _in_s4(section) else "evidence_rera"
    label = "S.4 Control" if agent == "s4_control" else "Evidence/RERA"
    weak = "" if relevant else " None of them passed the relevance threshold, so treat this choice with care."
    reason = (
        f"The best-matching passages come mostly from guidance tagged {section}, so the question was "
        f"sent to {label}.{weak}"
    )
    return Route(agent, section, reason, {k: round(v, 3) for k, v in votes.items()}, based_on)


def ask(
    m2: Member2Components,
    question: str,
    current_only: bool = False,
    use_reranker: bool | None = None,
) -> tuple[Route, list[Finding]]:
    """Search everything once, choose the section and agent, and return the agent's findings."""
    filters = SearchFilters(applicability_statuses=["current"] if current_only else [])
    result = m2.retrieval.retrieve(question, filters=filters, use_reranker=use_reranker)
    route = choose_route(result, m2.settings)

    if route.agent == "s4_control":
        agent: S4ControlAgent = m2.agents["s4_control"]  # type: ignore[assignment]
        topic = _SECTION_TO_TOPIC.get(route.ctd_section, S4Topic.GENERAL)
        findings = agent.assess(question, topic=topic, retrieved=result)
    else:
        rera: EvidenceReraAgent = m2.agents["evidence_rera"]  # type: ignore[assignment]
        findings = [rera.assess(question, route.ctd_section, use_section_filter=False, retrieved=result)]
    return route, findings
