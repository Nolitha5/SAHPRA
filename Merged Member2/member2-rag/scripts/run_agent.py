"""Run Evidence/RERA or S.4 Control from the command line and print the findings.

Examples:
    python scripts/run_agent.py evidence --section 3.2.S.4.3 \
        --question "What validation characteristics are expected for an assay procedure?"

    python scripts/run_agent.py s4 --topic specification \
        --question "Which tests should the drug substance specification contain?"

    # With structured sponsor data (see examples/s4_request.example.json):
    python scripts/run_agent.py s4 --request examples/s4_request.example.json

Output is the redacted finding JSON (sponsor content removed). Use --unredacted
only inside the assessor's secure environment.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.evidence_rera import EvidenceReraAgent
from app.agents.s4_control import S4ControlAgent, S4Topic
from app.config import load_settings
from app.logging_utils import configure_logging
from app.retrieval.retrieval_service import build_retrieval_service
from app.schemas import AgentRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("agent", choices=["evidence", "s4"])
    parser.add_argument("--question")
    parser.add_argument("--section", default="3.2.S.4", help="CTD section (evidence agent)")
    parser.add_argument("--topic", choices=[t.value for t in S4Topic], help="S.4 topic")
    parser.add_argument("--request", type=Path, help="AgentRequest JSON file")
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--unredacted", action="store_true")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.no_rerank:
        settings = settings.with_overrides(reranker_enabled=False)
    configure_logging(settings.log_level, settings.log_json)
    service = build_retrieval_service(settings)

    if args.request:
        request = AgentRequest(**json.loads(args.request.read_text(encoding="utf-8")))
    else:
        if not args.question:
            parser.error("--question is required unless --request is given")
        params = {"topic": args.topic} if args.topic else {}
        section = args.section
        if args.agent == "s4" and args.topic:
            from app.agents.s4_control import TOPIC_SECTIONS

            section = TOPIC_SECTIONS[S4Topic(args.topic)]
        request = AgentRequest(ctd_section=section, assessment_question=args.question, parameters=params)

    agent = EvidenceReraAgent(service) if args.agent == "evidence" else S4ControlAgent(service)
    findings = agent.run(request)
    dumped = [f.model_dump(mode="json") if args.unredacted else f.model_dump_redacted() for f in findings]
    print(json.dumps(dumped, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
