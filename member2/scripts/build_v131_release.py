"""Build SAHPRA_Member2_KnowledgeBase_Integration_v1.3.1.zip.

Intentionally EXCLUDES:
- local_indexes/  (ChromaDB index files — rebuild with scripts/build_real_chroma.py)
- models/          (BGE model weights ~1.3GB — auto-downloaded on first use)
- pharmacopoeia/incoming/raw_from_pharmacy/  (dossier PDFs — not redistributable)
- __pycache__/ .pytest_cache/ .mypy_cache/  (build artefacts)
- .git/            (not applicable — not a git repo)

Includes:
- All source code, tests, scripts
- artifacts/real_corpus/ (regulatory JSONL corpus)
- docs/ (18 documentation files)
- validation/ (all validation artefacts except large index files)
- examples/ (probe file)
- regulatory_sources/ (CSV inventory)
- pharmacopoeia/incoming/COPY_MANIFEST.json
- pharmacopoeia/quarantine/ (5 HTML files)
- pyproject.toml, MANIFEST.in, etc.
"""
from __future__ import annotations
import hashlib, zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
RELEASE_DIR = PROJECT / "releases"
ZIP_NAME = "SAHPRA_Member2_KnowledgeBase_Integration_v1.3.1.zip"

EXCLUDE_DIRS = {
    "local_indexes",
    "models",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    "venv",
    ".git",
    "node_modules",
}

EXCLUDE_SUBPATHS = {
    "pharmacopoeia/incoming/raw_from_pharmacy",
}

EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".egg-info"}


def should_exclude(rel: Path) -> bool:
    parts = rel.parts
    # Top-level excluded dirs
    if parts[0] in EXCLUDE_DIRS:
        return True
    # Specific subpath exclusions
    rel_str = rel.as_posix()
    for ex in EXCLUDE_SUBPATHS:
        if rel_str.startswith(ex):
            return True
    # Suffix
    if rel.suffix in EXCLUDE_SUFFIXES:
        return True
    # Hidden files
    if any(p.startswith(".") for p in parts):
        return True
    return False


def main() -> None:
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RELEASE_DIR / ZIP_NAME

    files_added = 0
    with zipfile.ZipFile(str(zip_path), "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(PROJECT.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(PROJECT)
            if should_exclude(rel):
                continue
            # Skip the releases dir itself (avoid recursion)
            if rel.parts[0] == "releases":
                continue
            zf.write(str(f), str(rel))
            files_added += 1

    sha = hashlib.sha256()
    with open(str(zip_path), "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            sha.update(block)
    digest = sha.hexdigest()
    size_mb = zip_path.stat().st_size / (1024 * 1024)

    print(f"ZIP: {zip_path}")
    print(f"Files: {files_added}")
    print(f"Size: {size_mb:.1f} MB")
    print(f"SHA-256: {digest}")

    # Write SHA sidecar
    sha_file = RELEASE_DIR / (ZIP_NAME + ".sha256")
    sha_file.write_text(f"{digest}  {ZIP_NAME}\n", encoding="utf-8")
    print(f"SHA file: {sha_file}")


if __name__ == "__main__":
    main()
