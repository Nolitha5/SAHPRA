"""Conversion between validated `PassageMetadata` and ChromaDB metadata.

ChromaDB metadata values must be str / int / float / bool and cannot be None.
So:
* missing optional fields are simply *omitted* (never stored as "" or 0,
  which would look like real values), and
* derived filter fields are added (`ctd_section_root`, `provenance_complete`).

When reading back, every stored record is re-validated with Pydantic, so a
corrupted or hand-edited database cannot silently produce fake provenance.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from app.schemas import PassageMetadata

# Derived keys we add for filtering; stripped again when reading back.
_DERIVED_KEYS = {"ctd_section_root", "ctd_part", "provenance_complete", "embedding_model"}


class MetadataCorruptionError(RuntimeError):
    """Raised when a stored record no longer passes schema validation."""


def ctd_section_root(section: str | None) -> str | None:
    """'3.2.S.4.1' -> '3.2.S.4' (first heading level below the module letter)."""
    if not section:
        return None
    parts = section.split(".")
    letter_idx = next((i for i, p in enumerate(parts) if p.isalpha()), None)
    if letter_idx is None:
        return section
    return ".".join(parts[: min(len(parts), letter_idx + 2)])


def ctd_part(section: str | None) -> str | None:
    """'3.2.S.4.1' -> '3.2.S' (the module part, up to the letter)."""
    if not section:
        return None
    parts = section.split(".")
    letter_idx = next((i for i, p in enumerate(parts) if p.isalpha()), None)
    if letter_idx is None:
        return None
    return ".".join(parts[: letter_idx + 1])


def to_chroma_metadata(meta: PassageMetadata, embedding_model: str) -> dict[str, Any]:
    """Flatten metadata for ChromaDB (no None values; enums as strings)."""
    raw = meta.model_dump(mode="json")
    flat: dict[str, Any] = {k: v for k, v in raw.items() if v is not None}
    root = ctd_section_root(meta.ctd_section)
    if root:
        flat["ctd_section_root"] = root
    part = ctd_part(meta.ctd_section)
    if part:
        flat["ctd_part"] = part
    flat["provenance_complete"] = meta.provenance_complete
    flat["embedding_model"] = embedding_model
    return flat


def from_chroma_metadata(stored: Mapping[str, Any]) -> PassageMetadata:
    """Rebuild and re-validate `PassageMetadata` from a stored ChromaDB record."""
    data = {k: v for k, v in stored.items() if k not in _DERIVED_KEYS}
    try:
        return PassageMetadata(**data)
    except ValidationError as exc:
        chunk_id = stored.get("chunk_id", "<unknown>")
        raise MetadataCorruptionError(
            f"Stored metadata for chunk {chunk_id} failed validation: {exc.error_count()} error(s). "
            "Re-index this passage from the processed source file."
        ) from exc
