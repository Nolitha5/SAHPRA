"""Build the knowledge base in one command: download, convert and index every source.

Reads the source list (default: sources/kb_v2_manifest.json), then
  1. downloads each PDF from its official "url" (skipped if the file is already there),
  2. converts the PDFs to passages (scripts/pdf_to_jsonl.py),
  3. embeds and stores them in ChromaDB (scripts/load_documents.py).

Run it again at any time: files already downloaded are not fetched again, and passages
that have not changed are not re-embedded.

Examples (from the member2-rag folder):
    python scripts/build_knowledge_base.py                 # everything
    python scripts/build_knowledge_base.py --download-only # just fetch the PDFs
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_settings

USER_AGENT = "Mozilla/5.0 (Agentic QA-RAG knowledge-base build)"


def _script(name: str):
    """Import a sibling script (scripts/ is not a package) to reuse its main()."""
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # must be registered before running: dataclasses look it up
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def download_sources(manifest: Path) -> list[str]:
    """Download every missing PDF listed in the manifest. Returns a list of problems."""
    problems = []
    for entry in json.loads(manifest.read_text(encoding="utf-8")):
        target = (manifest.parent / entry["pdf"]).resolve()
        version = entry.get("document_version") or ""
        label = f"{entry['issuing_organization']} {entry['source_identifier']} {version}".strip()
        if target.exists() and target.read_bytes()[:5] == b"%PDF-":
            print(f"  have      {label}")
            continue
        url = entry.get("url")
        if not url:
            problems.append(f"{label}: no 'url' in the manifest; place the PDF at {target}")
            continue
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=120) as response:
                data = response.read()
        except OSError as exc:
            problems.append(f"{label}: download failed ({exc.__class__.__name__}); try again or download {url}")
            continue
        if data[:5] != b"%PDF-":
            problems.append(f"{label}: {url} did not return a PDF")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        print(f"  download  {label} ({len(data) // 1024} KB)")
    return problems


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--manifest", type=Path, default=settings.sources_manifest)
    p.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "kb_v2_w300.jsonl")
    p.add_argument("--collection", default=settings.collection_name,
                   help=f"ChromaDB collection (default from .env: {settings.collection_name})")
    p.add_argument("--download-only", action="store_true")
    args = p.parse_args(argv)

    print(f"1/3 Downloading sources listed in {args.manifest.name}")
    problems = download_sources(args.manifest)
    if problems:
        print("\nSome sources are missing:\n  " + "\n  ".join(problems))
        return 1
    if args.download_only:
        return 0

    print(f"\n2/3 Converting PDFs to passages -> {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if _script("pdf_to_jsonl").main(["--manifest", str(args.manifest), "--output", str(args.output)]) != 0:
        print("Conversion failed; see the messages above.")
        return 1

    print(f"\n3/3 Embedding and storing passages in collection '{args.collection}' (several minutes on CPU)")
    code = _script("load_documents").main(["--input", str(args.output), "--collection", args.collection])
    if code == 0:
        print(f"\nDone. Make sure M2_COLLECTION_NAME={args.collection} in .env, then start the app: python -m app.api")
    return code


if __name__ == "__main__":
    sys.exit(main())
