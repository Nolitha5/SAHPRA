"""Load processed passages (JSONL from Member 3) into the ChromaDB knowledge base.

Examples (run from the member2-rag folder):
    python scripts/load_documents.py --input data/processed/passages.jsonl
    python scripts/load_documents.py --input data/processed/passages.jsonl --dry-run
    python scripts/load_documents.py --input data/processed/passages.jsonl --strict
    python scripts/load_documents.py --input examples/synthetic_passages.jsonl --collection demo_kb_small \
        --embedding-model BAAI/bge-small-en-v1.5

Exit codes: 0 = success, 1 = file unusable / strict-mode failure, 2 = some records rejected.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings
from app.embeddings.bge_embeddings import build_embedder
from app.knowledge_base.document_store import ChromaDocumentStore
from app.knowledge_base.indexing import InputFileError, index_jsonl, load_jsonl
from app.logging_utils import configure_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path, help="JSONL file of processed passages")
    parser.add_argument("--collection", help="override M2_COLLECTION_NAME")
    parser.add_argument("--embedding-model", help="override M2_EMBEDDING_MODEL")
    parser.add_argument("--strict", action="store_true", help="abort if any record is invalid")
    parser.add_argument("--dry-run", action="store_true", help="validate only; do not load models or write")
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args(argv)

    settings = load_settings()
    overrides = {}
    if args.collection:
        overrides["collection_name"] = args.collection
    if args.embedding_model:
        overrides["embedding_model"] = args.embedding_model
    settings = settings.with_overrides(**overrides).validate()
    configure_logging(settings.log_level, settings.log_json)

    try:
        if args.dry_run:
            loaded = load_jsonl(args.input)
            report = {
                "dry_run": True,
                "lines_read": loaded.lines_read,
                "valid_records": len(loaded.records),
                "rejected": len(loaded.errors),
                "rejected_details": [e.__dict__ for e in loaded.errors],
                "skipped_duplicates": len(loaded.skipped_duplicates),
            }
            print(json.dumps(report, indent=2))
            return 2 if loaded.errors else 0

        embedder = build_embedder(settings)
        store = ChromaDocumentStore(
            settings.chroma_dir, settings.collection_name, embedder.model_name, embedder.dimension
        )
        report = index_jsonl(args.input, store, embedder, strict=args.strict, batch_size=args.batch_size)
    except InputFileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    out = report.as_dict()
    out["collection"] = settings.collection_name
    out["embedding_model"] = settings.embedding_model
    print(json.dumps(out, indent=2))
    return 2 if report.rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
