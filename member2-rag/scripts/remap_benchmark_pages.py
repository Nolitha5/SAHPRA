"""Carry page-level benchmark labels over to a new edition of the same documents.

When a guideline is replaced by another edition or print (e.g. SAHPRA PEM-02 v8 -> v9,
or the ICH print of Q6A -> the EMA print), its page numbers change, so page labels in
the benchmark would point at the wrong pages. For every labelled page this script finds
the page of the *same source_identifier* in the new passages whose words overlap most
with the old page, and writes a NEW benchmark file. The original file is not changed.

Low-overlap matches are flagged in the report for a person to check. The remapped labels
keep the original `labelled_by` text plus a note: they are still draft labels.

Example (from the member2-rag folder):
    python scripts/remap_benchmark_pages.py --benchmark benchmarks/pilot_sahpra.jsonl \
        --old data/processed/sahpra_w300.jsonl data/processed/ich_w300.jsonl \
        --new data/processed/kb_v2_w300.jsonl --output benchmarks/pilot_sahpra_kb_v2.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

_WORD = re.compile(r"[a-z0-9]+")
SHINGLE = 5  # compare 5-word sequences: neighbouring pages share vocabulary but rarely whole phrases
MIN_CONFIDENT_OVERLAP = 0.5


def _shingles(text: str) -> set[str]:
    words = _WORD.findall(text.lower())
    return {" ".join(words[i : i + SHINGLE]) for i in range(max(0, len(words) - SHINGLE + 1))}


def page_words(paths: list[Path]) -> dict[tuple[str, int], set[str]]:
    """Set of 5-word phrases per (source_identifier, page)."""
    pages: dict[tuple[str, int], set[str]] = defaultdict(set)
    for path in paths:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                rec = json.loads(line)
                if rec.get("page_number") is None:
                    continue
                pages[(rec["source_identifier"], int(rec["page_number"]))] |= _shingles(rec["text"])
    return pages


def best_match(old: set[str], candidates: dict[int, set[str]]) -> tuple[int | None, float, float]:
    """(best page, its overlap, runner-up overlap). Overlap = share of the old page's words found."""
    if not old or not candidates:
        return None, 0.0, 0.0
    scored = sorted(((len(old & words) / len(old), page) for page, words in candidates.items()), reverse=True)
    runner_up = scored[1][0] if len(scored) > 1 else 0.0
    return scored[0][1], scored[0][0], runner_up


def remap(benchmark: Path, old: list[Path], new: list[Path], output: Path) -> dict:
    old_pages, new_pages = page_words(old), page_words(new)
    new_by_source: dict[str, dict[int, set[str]]] = defaultdict(dict)
    for (source, page), words in new_pages.items():
        new_by_source[source][page] = words

    report = {"benchmark": str(benchmark), "output": str(output), "labels": [], "needs_review": 0}
    items = []
    with benchmark.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            item = json.loads(line)
            remapped = []
            for ref in item.get("relevant_pages", []):
                key = (ref["source_identifier"], int(ref["page_number"]))
                candidates = new_by_source.get(ref["source_identifier"], {})
                page, score, runner_up = best_match(old_pages.get(key, set()), candidates)
                review = page is None or score < MIN_CONFIDENT_OVERLAP or (runner_up and score - runner_up < 0.05)
                report["needs_review"] += bool(review)
                report["labels"].append({
                    "question_id": item["question_id"], "source_identifier": ref["source_identifier"],
                    "old_page": key[1], "new_page": page, "overlap": round(score, 3),
                    "runner_up_overlap": round(runner_up, 3), "needs_review": bool(review),
                })
                new_ref = {"source_identifier": ref["source_identifier"], "page_number": page}
                if page is not None and new_ref not in remapped:
                    remapped.append(new_ref)
            item["relevant_pages"] = remapped
            note = "page labels carried over to the new edition by text overlap (scripts/remap_benchmark_pages.py)"
            item["labelled_by"] = f"{item.get('labelled_by') or 'unknown'}; {note}"
            items.append(item)

    output.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--benchmark", type=Path, required=True)
    p.add_argument("--old", type=Path, nargs="+", required=True, help="processed passages the labels were made on")
    p.add_argument("--new", type=Path, nargs="+", required=True, help="processed passages of the new knowledge base")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    if args.output.resolve() == args.benchmark.resolve():
        p.error("--output must be a new file; the original benchmark is never overwritten")
    report = remap(args.benchmark, args.old, args.new, args.output)
    print(json.dumps(report, indent=2))
    return 2 if report["needs_review"] else 0


if __name__ == "__main__":
    sys.exit(main())
