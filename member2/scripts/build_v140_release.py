"""Build releases/SAHPRA_Member2_Visual_KB_Acceptance_v1.4.0.zip"""
from __future__ import annotations
import hashlib, zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
OUT = PROJECT / "releases" / "SAHPRA_Member2_Visual_KB_Acceptance_v1.4.0.zip"

EXCLUDES = {
    "local_indexes",
    "models",
    "__pycache__",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
}

EXCLUDE_PATHS = {
    "pharmacopoeia/incoming/raw_from_pharmacy",
}


def should_exclude(rel: Path) -> bool:
    parts = rel.parts
    if any(p in EXCLUDES for p in parts):
        return True
    rel_str = str(rel).replace("\\", "/")
    if any(rel_str.startswith(ep) for ep in EXCLUDE_PATHS):
        return True
    return False


def build():
    files = []
    for f in sorted(PROJECT.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(PROJECT)
        if should_exclude(rel):
            continue
        # skip releases dir (don't include old ZIPs)
        if rel.parts[0] == "releases":
            continue
        files.append((f, rel))

    print(f"Including {len(files)} files…")
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f, rel in files:
            zf.write(f, rel)

    # SHA-256
    h = hashlib.sha256()
    with open(OUT, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    digest = h.hexdigest()

    sidecar = OUT.with_suffix(".zip.sha256")
    sidecar.write_text(f"{digest}  {OUT.name}\n", encoding="utf-8")

    size_mb = round(OUT.stat().st_size / 1_048_576, 1)
    print(f"Written: {OUT.relative_to(PROJECT)}")
    print(f"Files:   {len(files)}")
    print(f"Size:    {size_mb} MB")
    print(f"SHA-256: {digest}")
    return digest, len(files), size_mb


if __name__ == "__main__":
    build()
