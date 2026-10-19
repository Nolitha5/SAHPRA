"""Single entry point for Member 1's Orchestrator.

    from app.integration import create_member2_components
    m2 = create_member2_components()            # loads config from env/.env
    findings = m2.agents["evidence_rera"].run(request)   # -> list[Finding]
    result = m2.retrieval.retrieve("...", filters=SearchFilters(ctd_sections=["3.2.S.2"]))

* `m2.retrieval` is the SHARED retrieval service other members' agents should
  call (S.1, S.2, S.3, S.5, S.6, S.7 agents) instead of building their own.
* Every agent exposes `run(AgentRequest) -> list[Finding]`.
* Models load lazily on the first query, so creating the components is cheap.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.evidence_rera import EvidenceReraAgent
from app.agents.s4_control import S4ControlAgent
from app.config import Settings, get_settings
from app.logging_utils import configure_logging
from app.retrieval.retrieval_service import RetrievalService, build_retrieval_service


@dataclass
class Member2Components:
    settings: Settings
    retrieval: RetrievalService
    agents: dict = field(default_factory=dict)


def create_member2_components(settings: Settings | None = None) -> Member2Components:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    retrieval = build_retrieval_service(settings)
    agents = {
        EvidenceReraAgent.name: EvidenceReraAgent(retrieval, settings),
        S4ControlAgent.name: S4ControlAgent(retrieval, settings),
    }
    return Member2Components(settings=settings, retrieval=retrieval, agents=agents)
