"""Deterministic hashing helpers for content hashes and stable chunk IDs.

Kept in a tiny dependency-free module so both `schemas.py` and the knowledge
base can import it without circular imports.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalise_text(text: str) -> str:
    """Normalise Unicode (NFC) and collapse whitespace.

    Two passages that differ only in line breaks or spacing (common after PDF
    extraction) get the same content hash. Case and punctuation are preserved
    because they can change regulatory meaning (e.g. "NMT 0.1%" vs "nmt").
    """
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


def compute_content_hash(text: str) -> str:
    """SHA-256 hex digest of the normalised passage text."""
    return hashlib.sha256(normalise_text(text).encode("utf-8")).hexdigest()


def make_chunk_id(
    source_identifier: str,
    document_version: str | None,
    page_number: int | None,
    chunk_index: int | None,
    content_hash: str,
) -> str:
    """Build a stable chunk ID when Member 3 does not supply one.

    * If the chunk has a position (page + chunk_index) the ID is based on the
      position, so re-ingesting corrected text for the same position UPDATES
      the existing record instead of creating a duplicate.
    * Without a position, the content hash is used, so identical text from the
      same source always maps to the same ID.
    """
    if page_number is not None and chunk_index is not None:
        key = f"{source_identifier}|{document_version or ''}|p{page_number}|c{chunk_index}"
    else:
        key = f"{source_identifier}|{document_version or ''}|h{content_hash}"
    return "m2-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
