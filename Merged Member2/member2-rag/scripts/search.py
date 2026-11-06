"""Run one retrieval query against the knowledge base and print JSON.

Examples:
    python scripts/search.py "What should a drug substance specification include?" --section 3.2.S.4.1
    python scripts/search.py "analytical method validation" --no-rerank --final-k 3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings
from app.logging_utils import configure_logging
from app.retrieval.retrieval_service import build_retrieval_service
from app.schemas import SearchFilters


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query")
    parser.add_argument("--section", action="append", default=[], help="CTD section filter (repeatable)")
    parser.add_argument("--doc-type", action="append", default=[], help="document_type filter (repeatable)")
    parser.add_argument("--org", action="append", default=[], help="issuing_organization filter (repeatable)")
    parser.add_argument("--current-only", action="store_true", help="only applicability_status=current")
    parser.add_argument("--candidate-k", type=int)
    parser.add_argument("--final-k", type=int)
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--show-text", action="store_true", help="print full passage text")
    args = parser.parse_args(argv)

    settings = load_settings()
    if args.no_rerank:
        settings = settings.with_overrides(reranker_enabled=False)
    configure_logging(settings.log_level, settings.log_json)
    service = build_retrieval_service(settings)

    filters = SearchFilters(
        ctd_sections=args.section,
        document_types=args.doc_type,
        issuing_organizations=args.org,
        applicability_statuses=["current"] if args.current_only else [],
    )
    result = service.retrieve(args.query, filters=filters, candidate_k=args.candidate_k, final_k=args.final_k)
    data = result.model_dump(mode="json")
    if not args.show_text:
        for p in data["passages"]:
            p["text"] = p["text"][:200] + ("..." if len(p["text"]) > 200 else "")
    print(json.dumps(data, indent=2))
    if result.is_empty_knowledge_base:
        print("NOTE: the knowledge base is empty. Load passages first.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
